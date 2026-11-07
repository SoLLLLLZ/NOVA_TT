import type { ModelLook } from "../models";
import { Wordmark } from "./Header";

type Props = {
  look: ModelLook;
  /** "select": bracketed preview on screen 1. "hero": framed card on the optimized screen. */
  variant: "select" | "hero";
  modelKey: string;
};

/** The model's car on a cyan grid floor with a soft reflection. */
export function CarStage({ look, variant, modelKey }: Props) {
  return (
    <div className={`stage stage--${variant}`}>
      {variant === "select" ? (
        <>
          <span className="stage__corner stage__corner--tl" aria-hidden="true" />
          <span className="stage__corner stage__corner--tr" aria-hidden="true" />
          <span className="stage__corner stage__corner--bl" aria-hidden="true" />
          <span className="stage__corner stage__corner--br" aria-hidden="true" />
          <span className="stage__plus stage__plus--l" aria-hidden="true" />
          <span className="stage__plus stage__plus--r" aria-hidden="true" />
        </>
      ) : (
        <>
          <div className="stage__brand">
            <Wordmark />
          </div>
          <span className="stage__bar stage__bar--l" aria-hidden="true" />
          <span className="stage__bar stage__bar--r" aria-hidden="true" />
        </>
      )}
      <div className="stage__floor" aria-hidden="true" />
      <div className="stage__car" key={modelKey}>
        <img src={look.car} alt={`${look.name} race car`} className="stage__img" draggable={false} />
        <img src={look.car} alt="" aria-hidden="true" className="stage__reflection" draggable={false} />
      </div>
    </div>
  );
}
