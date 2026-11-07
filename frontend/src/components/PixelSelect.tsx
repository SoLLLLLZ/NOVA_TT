import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { CaretIcon, CheckIcon } from "./icons";

export type SelectOption = { value: string; label: string; hint?: string; disabled?: boolean };

type Props = {
  label: string;
  value: string | null;
  options: SelectOption[];
  onChange: (value: string) => void;
  placeholder?: string;
  compact?: boolean;
  wideMenu?: boolean;
  disabled?: boolean;
};

/** Accessible listbox dropdown (button + listbox, arrow/Home/End/Enter/Escape/Tab). */
export function PixelSelect({ label, value, options, onChange, placeholder = "Select…", compact, wideMenu, disabled }: Props) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const selected = options.find((option) => option.value === value);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  useEffect(() => {
    if (open) listRef.current?.focus();
  }, [open]);

  const enabled = options.map((option, index) => (option.disabled ? -1 : index)).filter((index) => index >= 0);

  const openList = () => {
    const current = options.findIndex((option) => option.value === value);
    setActive(current >= 0 ? current : enabled[0] ?? 0);
    setOpen(true);
  };

  const close = (refocus = true) => {
    setOpen(false);
    if (refocus) buttonRef.current?.focus();
  };

  const choose = (index: number) => {
    const option = options[index];
    if (!option || option.disabled) return;
    onChange(option.value);
    close();
  };

  const move = (delta: number) => {
    const position = enabled.indexOf(active);
    const next = enabled[Math.min(enabled.length - 1, Math.max(0, position + delta))];
    if (next !== undefined) setActive(next);
  };

  const onButtonKey = (event: KeyboardEvent) => {
    if (["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) {
      event.preventDefault();
      openList();
    }
  };

  const onListKey = (event: KeyboardEvent) => {
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        move(1);
        break;
      case "ArrowUp":
        event.preventDefault();
        move(-1);
        break;
      case "Home":
        event.preventDefault();
        setActive(enabled[0] ?? 0);
        break;
      case "End":
        event.preventDefault();
        setActive(enabled[enabled.length - 1] ?? 0);
        break;
      case "Enter":
      case " ":
        event.preventDefault();
        choose(active);
        break;
      case "Escape":
        event.preventDefault();
        close();
        break;
      case "Tab":
        close(false);
        break;
    }
  };

  return (
    <div className={`pselect${compact ? " pselect--compact" : ""}${wideMenu ? " pselect--wide-menu" : ""}${open ? " is-open" : ""}`} ref={rootRef}>
      <span className="pselect__label" id={`${id}-label`}>
        {label}
      </span>
      <button
        ref={buttonRef}
        type="button"
        className="pselect__button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-labelledby={`${id}-label ${id}-value`}
        disabled={disabled}
        onClick={() => (open ? close() : openList())}
        onKeyDown={onButtonKey}
      >
        <span id={`${id}-value`} className="pselect__value">
          {selected?.label ?? placeholder}
        </span>
        <CaretIcon size={12} className="pselect__caret" />
      </button>
      {open && (
        <ul
          ref={listRef}
          className="pselect__list"
          role="listbox"
          tabIndex={-1}
          aria-labelledby={`${id}-label`}
          aria-activedescendant={`${id}-opt-${active}`}
          onKeyDown={onListKey}
        >
          {options.map((option, index) => (
            <li
              key={option.value}
              id={`${id}-opt-${index}`}
              role="option"
              aria-selected={option.value === value}
              aria-disabled={option.disabled || undefined}
              className={[
                "pselect__option",
                index === active ? "is-active" : "",
                option.value === value ? "is-selected" : "",
                option.disabled ? "is-disabled" : "",
              ].join(" ")}
              onMouseEnter={() => !option.disabled && setActive(index)}
              onClick={() => choose(index)}
            >
              <span className="pselect__option-text">
                <span>{option.label}</span>
                {option.hint && <span className="pselect__hint">{option.hint}</span>}
              </span>
              {option.value === value && <CheckIcon size={12} />}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
