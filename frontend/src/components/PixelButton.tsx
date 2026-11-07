import type { ButtonHTMLAttributes, CSSProperties, ReactNode } from "react";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant: "primary" | "outline";
  icon?: ReactNode;
  accent?: { fill: string; ink: string };
};

export function PixelButton({ variant, icon, accent, children, className, style, ...rest }: Props) {
  const vars = accent ? ({ "--btn-fill": accent.fill, "--btn-ink": accent.ink } as CSSProperties) : undefined;
  return (
    <button type="button" className={`pbtn pbtn--${variant} ${className ?? ""}`} style={{ ...vars, ...style }} {...rest}>
      {icon && (
        <span className="pbtn__icon" aria-hidden="true">
          {icon}
        </span>
      )}
      {icon && variant === "primary" && <span className="pbtn__divider" aria-hidden="true" />}
      <span className="pbtn__text">{children}</span>
    </button>
  );
}
