# BLOCKED

## 已解除的白名单扩展

- `backend/app/main.py` 的发布版本升级为 v5.20.0 后，既有 `backend/tests/test_api.py::test_health_endpoint` 必须同步更新唯一一条 `release_version` 断言，否则“全部版本号更新”和“全量回归无新失败”无法同时成立。按任务的“确需扩大白名单先写 BLOCKED”要求，扩展仅限该断言，不删除、不跳过、不放宽任何业务断言。

## 当前阻塞

无。
