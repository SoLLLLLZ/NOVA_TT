import type { CSSProperties } from "react";
import type { StatusResponse } from "../api/types";
import { CarStage } from "../components/CarStage";
import { Header } from "../components/Header";
import { FlagIcon } from "../components/icons";
import { PixelButton } from "../components/PixelButton";
import { PixelSelect } from "../components/PixelSelect";
import { CLUSTERS } from "../config";
import { gpuLabel, gpuTypes } from "../lib/format";
import { lookFor } from "../models";

type Props = {
  status: StatusResponse | null;
  offline: boolean;
  clusterId: string;
  gpuType: string | null;
  model: string;
  onCluster: (id: string) => void;
  onGpu: (type: string) => void;
  onModel: (id: string) => void;
  onOptimize: () => void;
};

export function SelectScreen({ status, offline, clusterId, gpuType, model, onCluster, onGpu, onModel, onOptimize }: Props) {
  const detecting = status === null;
  const catalog = status?.models ?? [];
  const selected = catalog.find((m) => m.id === model);
  const look = lookFor(model, selected?.display_name);
  const types = status ? gpuTypes(status.all_gpus, catalog.map((m) => m.requirements.gpu_type)) : [];
  const cluster = CLUSTERS.find((c) => c.id === clusterId);
  const clusterSupported = !!cluster?.targetId && cluster.targetId === status?.target_id;
  // installed may be null (not checked yet); only an explicit false blocks Optimize.
  const canOptimize = !detecting && !offline && !!selected && selected.installed !== false && !!gpuType && clusterSupported;

  let note: string | null = null;
  if (selected && selected.installed === false) note = "This model isn't installed on the backend.";
  else if (selected && !selected.ready && selected.readiness_reasons.length) note = selected.readiness_reasons[0];
  else if (selected && gpuType && selected.requirements.gpu_type !== gpuType)
    note = `Tested on ${selected.requirements.gpu_type}; ${gpuType} has no verified profile.`;

  return (
    <main className="screen screen--select" style={{ "--accent": look.accent } as CSSProperties}>
      <Header gpu={gpuType ? gpuLabel(gpuType, status?.all_gpus) : null} connection={offline ? "offline" : detecting ? "detecting" : "connected"} boltColor={look.accent} />

      <div className="select-row">
        <PixelSelect
          compact
          label="Cluster"
          value={clusterId}
          onChange={onCluster}
          options={CLUSTERS.map((c) => ({ value: c.id, label: c.name, hint: c.note, disabled: !c.targetId }))}
        />
        <PixelSelect
          compact
          label="GPU"
          value={gpuType}
          disabled={detecting}
          placeholder={detecting ? "Detecting…" : "No GPU"}
          onChange={onGpu}
          options={types.map((type) => ({ value: type, label: gpuLabel(type, status?.all_gpus) }))}
        />
      </div>

      <h1 className="title">Choose your model.</h1>
      <PixelSelect
        label="Model"
        value={model}
        disabled={detecting}
        onChange={onModel}
        options={catalog.map((m) => ({ value: m.id, label: lookFor(m.id, m.display_name).name }))}
      />

      <CarStage look={look} variant="select" modelKey={model} />
      <div className="car-caption">
        <p className="car-caption__name">{look.name}</p>
        {note && <p className="note">{note}</p>}
      </div>

      <PixelButton
        variant="primary"
        icon={<FlagIcon size={22} />}
        accent={{ fill: look.accent, ink: look.accentInk }}
        disabled={!canOptimize}
        onClick={onOptimize}
      >
        PITSTOP · OPTIMIZE
      </PixelButton>
      <p className="helper">{detecting ? "Detecting GPU…" : "Changing the model changes your car."}</p>
    </main>
  );
}
