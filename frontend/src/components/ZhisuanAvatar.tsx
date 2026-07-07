import "./ZhisuanAvatar.css";

export type ZhisuanAvatarState =
  | "idle"
  | "listening"
  | "thinking"
  | "processing"
  | "warning"
  | "error"
  | "success";

export type ZhisuanAvatarSize = "compact" | "normal" | "large";

export interface ZhisuanAvatarProps {
  state?: ZhisuanAvatarState;
  size?: ZhisuanAvatarSize;
  label?: string;
  className?: string;
}

const STATE_LABELS: Record<ZhisuanAvatarState, string> = {
  idle: "智算待命中",
  listening: "智算正在听取输入",
  thinking: "智算正在思考",
  processing: "智算正在处理",
  warning: "智算发现需复核项",
  error: "智算处理异常",
  success: "智算已完成",
};

export function ZhisuanAvatar({
  state = "idle",
  size = "normal",
  label,
  className,
}: ZhisuanAvatarProps) {
  const classNames = [
    "zhisuan-avatar",
    `zhisuan-avatar--${size}`,
    className,
  ].filter(Boolean).join(" ");
  const stateLabel = label ?? STATE_LABELS[state];

  return (
    <span
      className={classNames}
      data-state={state}
      role="img"
      aria-label={stateLabel}
      title={stateLabel}
    >
      <svg
        className="zhisuan-avatar__svg"
        viewBox="0 0 100 100"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <circle
          className="zhisuan-avatar__ring"
          cx="50"
          cy="50"
          r="41"
          stroke="#2563EB"
          strokeWidth="4"
          strokeLinecap="round"
          strokeDasharray="28 220"
        />
        <rect
          className="zhisuan-avatar__shell"
          x="22"
          y="22"
          width="56"
          height="56"
          rx="18"
          fill="#FFFFFF"
          stroke="#D7DEE8"
          strokeWidth="3"
        />
        <rect
          className="zhisuan-avatar__screen"
          x="32"
          y="34"
          width="36"
          height="25"
          rx="10"
          fill="#F8FBFF"
          stroke="#DBEAFE"
          strokeWidth="2"
        />
        <circle
          className="zhisuan-avatar__status-dot"
          cx="73"
          cy="27"
          r="5.2"
          fill="#38BDF8"
          stroke="#FFFFFF"
          strokeWidth="2.4"
        />
        <g className="zhisuan-avatar__magnifier" transform="translate(68 58)">
          <circle
            className="zhisuan-avatar__magnifier-lens"
            cx="-2"
            cy="-2"
            r="7"
            stroke="#2563EB"
            strokeWidth="2.6"
          />
          <path
            className="zhisuan-avatar__magnifier-handle"
            d="M3.4 3.4L10 10"
            stroke="#2563EB"
            strokeWidth="2.8"
            strokeLinecap="round"
          />
        </g>
        <circle
          className="zhisuan-avatar__eye"
          cx="43"
          cy="46"
          r="2.4"
          fill="#2563EB"
        />
        <circle
          className="zhisuan-avatar__eye"
          cx="57"
          cy="46"
          r="2.4"
          fill="#2563EB"
        />
        <path
          className="zhisuan-avatar__z"
          d="M42 63H59L43 73H60"
          stroke="#94A3B8"
          strokeWidth="3.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <line
          className="zhisuan-avatar__scan"
          x1="36"
          y1="39"
          x2="64"
          y2="39"
          stroke="#60A5FA"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <path
          className="zhisuan-avatar__check"
          d="M69 25.5L72 28.5L78 21.5"
          stroke="#16A34A"
          strokeWidth="2.7"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          className="zhisuan-avatar__warning"
          d="M73 23.5V29.5"
          stroke="#F59E0B"
          strokeWidth="2.8"
          strokeLinecap="round"
        />
        <circle
          className="zhisuan-avatar__warning"
          cx="73"
          cy="33.5"
          r="1.2"
          fill="#F59E0B"
        />
        <path
          className="zhisuan-avatar__error"
          d="M69.5 23.5L76.5 30.5M76.5 23.5L69.5 30.5"
          stroke="#B42318"
          strokeWidth="2.6"
          strokeLinecap="round"
        />
      </svg>
    </span>
  );
}

export default ZhisuanAvatar;
