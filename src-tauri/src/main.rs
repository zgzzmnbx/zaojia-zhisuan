use std::{
    env,
    ffi::OsString,
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    net::{SocketAddr, TcpStream},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::{Duration, Instant},
};

use tauri::{path::BaseDirectory, Manager, RunEvent, WebviewUrl, WebviewWindowBuilder};

const APP_URL: &str = "http://127.0.0.1:8000/";
const HEALTH_HOST: [u8; 4] = [127, 0, 0, 1];
const BACKEND_PORT: u16 = 8000;
const BACKEND_START_TIMEOUT: Duration = Duration::from_secs(75);

struct BackendState {
    child: Mutex<Option<Child>>,
    pid_path: Option<PathBuf>,
}

impl BackendState {
    fn reused_existing() -> Self {
        Self {
            child: Mutex::new(None),
            pid_path: None,
        }
    }

    fn spawned(child: Child, pid_path: PathBuf) -> Self {
        Self {
            child: Mutex::new(Some(child)),
            pid_path: Some(pid_path),
        }
    }

    fn stop(&self) {
        let Ok(mut guard) = self.child.lock() else {
            return;
        };
        if let Some(child) = guard.as_mut() {
            let _ = child.kill();
            let _ = child.wait();
        }
        *guard = None;
        if let Some(pid_path) = &self.pid_path {
            let _ = fs::remove_file(pid_path);
        }
    }
}

impl Drop for BackendState {
    fn drop(&mut self) {
        self.stop();
    }
}

fn main() {
    let app = tauri::Builder::default()
        .setup(|app| {
            let backend_state = ensure_backend(app)?;
            app.manage(backend_state);

            WebviewWindowBuilder::new(
                app,
                "main",
                WebviewUrl::External(APP_URL.parse().map_err(boxed_error)?),
            )
            .title("造价智算")
            .inner_size(1360.0, 900.0)
            .min_inner_size(1100.0, 720.0)
            .resizable(true)
            .center()
            // Tauri intercepts OS file drops by default. Disable that handler so the
            // existing React drop zones can receive HTML5 File objects in WebView2.
            .disable_drag_drop_handler()
            .build()?;

            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(
                event,
                tauri::WindowEvent::CloseRequested { .. } | tauri::WindowEvent::Destroyed
            ) {
                let state = window.app_handle().state::<BackendState>();
                state.stop();
            }
        })
        .build(tauri::generate_context!())
        .expect("failed to build zaojiazhisuan desktop shell");

    app.run(|app_handle, event| {
        if matches!(event, RunEvent::ExitRequested { .. } | RunEvent::Exit) {
            let state = app_handle.state::<BackendState>();
            state.stop();
        }
    });
}

fn ensure_backend(app: &tauri::App) -> Result<BackendState, Box<dyn std::error::Error>> {
    if is_backend_healthy() {
        return Ok(BackendState::reused_existing());
    }
    if is_backend_port_open() {
        return Err(boxed_error(format!(
            "端口 {BACKEND_PORT} 已被占用，但不是造价智算后端；请先关闭占用进程。"
        )));
    }

    let app_root = resolve_app_root(app)?;
    let (mut child, pid_path) = spawn_backend(&app_root)?;
    if let Err(error) = wait_for_backend(Some(&mut child), BACKEND_START_TIMEOUT) {
        let _ = child.kill();
        let _ = child.wait();
        let _ = fs::remove_file(pid_path);
        return Err(error);
    }

    Ok(BackendState::spawned(child, pid_path))
}

fn resolve_app_root(app: &tauri::App) -> Result<PathBuf, Box<dyn std::error::Error>> {
    let mut candidates = Vec::new();

    if let Ok(configured) = env::var("GUANKAN_APP_ROOT") {
        if !configured.trim().is_empty() {
            candidates.push(PathBuf::from(configured.trim()));
        }
    }

    if let Ok(current_dir) = env::current_dir() {
        add_path_and_ancestors(&mut candidates, current_dir);
    }

    if let Ok(current_exe) = env::current_exe() {
        add_path_and_ancestors(&mut candidates, current_exe);
    }

    if let Ok(resource_marker) = app
        .path()
        .resolve("backend/app/main.py", BaseDirectory::Resource)
    {
        if resource_marker.exists() {
            if let Some(root) = resource_marker
                .parent()
                .and_then(Path::parent)
                .and_then(Path::parent)
            {
                candidates.push(root.to_path_buf());
            }
        }
    }

    for candidate in candidates {
        if is_app_root(&candidate) {
            return Ok(candidate);
        }
    }

    Err(boxed_error(
        "未找到造价智算应用根目录。请在项目根目录运行，或设置 GUANKAN_APP_ROOT。",
    ))
}

fn add_path_and_ancestors(candidates: &mut Vec<PathBuf>, path: PathBuf) {
    let start = if path.is_file() {
        path.parent().map(Path::to_path_buf)
    } else {
        Some(path)
    };
    if let Some(start) = start {
        for ancestor in start.ancestors() {
            candidates.push(ancestor.to_path_buf());
        }
    }
}

fn is_app_root(path: &Path) -> bool {
    let has_backend = path.join("backend").join("app").join("main.py").exists();
    let has_frontend = frontend_static_dir(path).is_some();
    has_backend && has_frontend
}

fn frontend_static_dir(app_root: &Path) -> Option<PathBuf> {
    let dist = app_root.join("frontend").join("dist");
    if dist.join("index.html").exists() {
        return Some(dist);
    }
    let web = app_root.join("web");
    if web.join("index.html").exists() {
        return Some(web);
    }
    None
}

fn spawn_backend(app_root: &Path) -> Result<(Child, PathBuf), Box<dyn std::error::Error>> {
    let runtime_dir = app_root.join(".runtime").join("logs");
    fs::create_dir_all(&runtime_dir)?;
    let stdout = open_log_file(&runtime_dir.join("tauri-backend.log"))?;
    let stderr = open_log_file(&runtime_dir.join("tauri-backend-error.log"))?;
    let pid_path = app_root.join(".runtime").join("tauri-backend.pid");
    let python = resolve_python(app_root);
    let frontend_dir = frontend_static_dir(app_root).ok_or_else(|| {
        boxed_error("未找到前端静态目录 frontend/dist/，请先运行 npm run frontend:build。")
    })?;

    let mut command = Command::new(&python);
    command
        .current_dir(app_root)
        .arg("-m")
        .arg("uvicorn")
        .arg("app.main:app")
        .arg("--host")
        .arg("127.0.0.1")
        .arg("--port")
        .arg(BACKEND_PORT.to_string())
        .arg("--app-dir")
        .arg("backend")
        .env("GUANKAN_FRONTEND_DIR", frontend_dir)
        .env("PYTHONUTF8", "1")
        .stdin(Stdio::null())
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::from(stderr));

    apply_pythonpath(app_root, &mut command);

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        command.creation_flags(CREATE_NO_WINDOW);
    }

    let child = command
        .spawn()
        .map_err(|error| boxed_error(format!("后端启动失败：{error}；Python={}", python.display())))?;
    fs::write(&pid_path, child.id().to_string())?;
    Ok((child, pid_path))
}

fn resolve_python(app_root: &Path) -> PathBuf {
    #[cfg(windows)]
    let portable = app_root.join("runtime").join("python").join("python.exe");
    #[cfg(not(windows))]
    let portable = app_root.join("runtime").join("python").join("bin").join("python");

    if portable.exists() {
        return portable;
    }

    if let Ok(configured) = env::var("PYTHON") {
        if !configured.trim().is_empty() {
            return PathBuf::from(configured.trim());
        }
    }

    PathBuf::from("python")
}

fn apply_pythonpath(app_root: &Path, command: &mut Command) {
    let mut entries = Vec::new();
    let python_libs = app_root.join("runtime").join("python-libs");
    if python_libs.exists() {
        entries.push(python_libs.into_os_string());
    }
    entries.push(app_root.join("backend").into_os_string());

    if let Some(existing) = env::var_os("PYTHONPATH") {
        entries.push(existing);
    }

    command.env("PYTHONPATH", join_os_paths(entries));
}

fn join_os_paths(entries: Vec<OsString>) -> OsString {
    #[cfg(windows)]
    const SEPARATOR: &str = ";";
    #[cfg(not(windows))]
    const SEPARATOR: &str = ":";

    let mut value = OsString::new();
    for (index, entry) in entries.into_iter().enumerate() {
        if index > 0 {
            value.push(SEPARATOR);
        }
        value.push(entry);
    }
    value
}

fn wait_for_backend(
    mut child: Option<&mut Child>,
    timeout: Duration,
) -> Result<(), Box<dyn std::error::Error>> {
    let deadline = Instant::now() + timeout;
    loop {
        if is_backend_healthy() {
            return Ok(());
        }

        if let Some(process) = child.as_deref_mut() {
            if let Some(status) = process.try_wait()? {
                return Err(boxed_error(format!(
                    "后端进程提前退出，状态码：{status}。请查看 .runtime/logs/tauri-backend-error.log。"
                )));
            }
        }

        if Instant::now() >= deadline {
            return Err(boxed_error(
                "后端 75 秒内未通过健康检查。请查看 .runtime/logs/tauri-backend.log。",
            ));
        }

        thread::sleep(Duration::from_millis(500));
    }
}

fn is_backend_port_open() -> bool {
    TcpStream::connect_timeout(
        &SocketAddr::from((HEALTH_HOST, BACKEND_PORT)),
        Duration::from_millis(500),
    )
    .is_ok()
}

fn is_backend_healthy() -> bool {
    let addr = SocketAddr::from((HEALTH_HOST, BACKEND_PORT));
    let Ok(mut stream) = TcpStream::connect_timeout(&addr, Duration::from_millis(800)) else {
        return false;
    };

    let _ = stream.set_read_timeout(Some(Duration::from_millis(1200)));
    let _ = stream.set_write_timeout(Some(Duration::from_millis(800)));
    if stream
        .write_all(b"GET /api/health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
        .is_err()
    {
        return false;
    }

    let mut response = String::new();
    if stream.read_to_string(&mut response).is_err() {
        return false;
    }

    response.contains("\"status\":\"ok\"") && response.contains("\"service\":\"guankanzhisuan\"")
}

fn open_log_file(path: &Path) -> Result<File, Box<dyn std::error::Error>> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(boxed_error)
}

fn boxed_error(error: impl ToString) -> Box<dyn std::error::Error> {
    Box::new(std::io::Error::new(
        std::io::ErrorKind::Other,
        error.to_string(),
    ))
}
