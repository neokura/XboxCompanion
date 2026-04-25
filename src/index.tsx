import {
  definePlugin,
  PanelSection,
  PanelSectionRow,
  ButtonItem,
  ToggleField,
  staticClasses,
} from "@decky/ui";
import { callable, toaster } from "@decky/api";

const { useEffect, useState } = window.SP_REACT;
type VFC<P = {}> = (props: P) => JSX.Element | null;

const PLUGIN_NAME = "Xbox Companion";
const RGB_PRESETS = ["#FF0000", "#00B7FF", "#00FF85", "#FFFFFF"];

const getDashboardState = callable<[], DashboardState>("get_dashboard_state");
const getOptimizationStates = callable<[], OptimizationData>(
  "get_optimization_states"
);
const setOptimizationEnabled = callable<[string, boolean], boolean>(
  "set_optimization_enabled"
);
const getInformationState = callable<[], InformationState>(
  "get_information_state"
);
const setPerformanceProfile = callable<[string], boolean>("set_performance_profile");
const setCpuBoostEnabled = callable<[boolean], boolean>("set_cpu_boost_enabled");
const setSmtEnabled = callable<[boolean], boolean>("set_smt_enabled");
const setRgbEnabled = callable<[boolean], boolean>("set_rgb_enabled");
const setRgbColor = callable<[string], boolean>("set_rgb_color");
const setDisplaySyncSetting = callable<[string, boolean], boolean>(
  "set_display_sync_setting"
);
const setFpsLimit = callable<[number], boolean>("set_fps_limit");
const setChargeLimitEnabled = callable<[boolean], boolean>("set_charge_limit_enabled");

interface PerformanceMode {
  id: string;
  label: string;
  native_id: string;
  description: string;
  available: boolean;
  active: boolean;
}

interface AvailabilityToggle {
  available: boolean;
  enabled: boolean;
  status: string;
  details: string;
  capable?: boolean;
  active?: boolean;
}

interface RgbState {
  available: boolean;
  enabled: boolean;
  color: string;
  presets: string[];
  details: string;
}

interface FpsLimitState {
  available: boolean;
  current: number;
  requested?: number;
  is_live?: boolean;
  presets: number[];
  status: string;
  details: string;
}

interface ChargeLimitState {
  available: boolean;
  enabled: boolean;
  limit: number;
  status: string;
  details: string;
}

interface DashboardState {
  performance_modes: PerformanceMode[];
  active_mode: string;
  profiles_available: boolean;
  profiles_status: string;
  cpu_boost: AvailabilityToggle;
  smt: AvailabilityToggle;
  rgb: RgbState;
  vrr: AvailabilityToggle;
  vsync: AvailabilityToggle & { allow_tearing?: boolean };
  fps_limit: FpsLimitState;
  charge_limit: ChargeLimitState;
}

interface OptimizationState {
  key: string;
  name: string;
  description: string;
  enabled: boolean;
  active: boolean;
  available: boolean;
  needs_reboot: boolean;
  details: string;
  risk_note: string;
  status: string;
}

interface OptimizationData {
  states: OptimizationState[];
}

interface DeviceInfo {
  friendly_name: string;
  board_name: string;
  product_name: string;
  product_family?: string;
  sys_vendor: string;
  variant: string;
  device_family: string;
  support_level: string;
  platform_supported?: boolean;
  platform_support_reason?: string;
  steamos_version: string;
  bios_version: string;
  serial: string;
  cpu: string;
  gpu: string;
  kernel: string;
  memory_total: string;
}

interface BatteryInfo {
  present: boolean;
  status: string;
  capacity: number;
  health: number;
  cycle_count: number;
  voltage: number;
  current: number;
  temperature: number;
  design_capacity: number;
  full_capacity: number;
  charge_limit: number;
  time_to_empty: string;
  time_to_full: string;
}

interface InformationState {
  device: DeviceInfo;
  battery: BatteryInfo;
  performance: {
    current_profile: string;
    available_native: string[];
    status: string;
  };
  display: {
    vrr: AvailabilityToggle;
    vsync: AvailabilityToggle;
  };
  temperatures: {
    tdp: number;
    cpu: number;
    gpu: number;
    gpu_clock: number;
  };
  optimizations: OptimizationState[];
  hardware_controls: Record<string, boolean>;
  fps_limit: FpsLimitState;
}

type ViewName = "dashboard" | "optimizations" | "information";

const viewTitleStyle: React.CSSProperties = {
  fontSize: "18px",
  fontWeight: 700,
  color: "#ffffff",
};

const subtextStyle: React.CSSProperties = {
  fontSize: "12px",
  color: "#8b929a",
  lineHeight: 1.4,
};

const cardStyle: React.CSSProperties = {
  background: "linear-gradient(180deg, rgba(36,42,49,0.95), rgba(25,29,35,0.95))",
  border: "1px solid rgba(100, 116, 139, 0.35)",
  borderRadius: "14px",
  padding: "14px",
  marginBottom: "12px",
};

const statusRowStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  gap: "12px",
  marginBottom: "6px",
};

const infoLabelStyle: React.CSSProperties = {
  color: "#8b929a",
  fontSize: "12px",
};

const infoValueStyle: React.CSSProperties = {
  color: "#ffffff",
  fontSize: "12px",
  textAlign: "right",
};

const presetGridStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
  gap: "8px",
  width: "100%",
};

const presetButtonStyle = (active: boolean): React.CSSProperties => ({
  borderRadius: "10px",
  padding: "10px 8px",
  textAlign: "center",
  fontSize: "12px",
  fontWeight: 700,
  color: active ? "#0f172a" : "#ffffff",
  background: active ? "#60a5fa" : "rgba(51, 65, 85, 0.85)",
  border: active
    ? "1px solid rgba(147, 197, 253, 0.8)"
    : "1px solid rgba(100, 116, 139, 0.4)",
});

const modeButtonStyle = (active: boolean, disabled: boolean): React.CSSProperties => ({
  width: "100%",
  borderRadius: "12px",
  padding: "12px",
  background: active
    ? "linear-gradient(180deg, #60a5fa, #3b82f6)"
    : "linear-gradient(180deg, rgba(51,65,85,0.9), rgba(30,41,59,0.9))",
  border: active
    ? "1px solid rgba(191, 219, 254, 0.9)"
    : "1px solid rgba(100, 116, 139, 0.35)",
  opacity: disabled ? 0.45 : 1,
});

const statusColor = (status: string): string => {
  switch (status) {
    case "active":
      return "#4ade80";
    case "configured":
      return "#60a5fa";
    case "reboot-required":
      return "#f59e0b";
    case "unavailable":
      return "#f87171";
    default:
      return "#cbd5e1";
  }
};

const formatToggleLabel = (
  title: string,
  setting?: AvailabilityToggle,
  unavailableLabel?: string
): string => {
  if (!setting?.available) {
    return unavailableLabel || `${title}: unavailable`;
  }
  return `${title}: ${setting.enabled ? "enabled" : "disabled"}`;
};

const formatFpsLabel = (value: number): string =>
  value === 0 ? "No limit / Disabled" : `${value} FPS`;

const hardwareControlLabels: Record<string, string> = {
  performance_profiles: "SteamOS profiles",
  cpu_boost: "CPU Boost",
  smt: "SMT",
  charge_limit: "Charge limit",
  rgb: "RGB",
  vrr: "VRR",
  vsync: "V-Sync",
  fps_limit: "Max Framerate",
  optimizations: "Optimizations",
};

const formatNumber = (value: number, unit: string): string =>
  Number.isFinite(value) && value > 0 ? `${value.toFixed(1)} ${unit}` : "Unknown";

const formatDisplayStatus = (setting?: AvailabilityToggle): string => {
  if (!setting?.available) {
    return setting?.capable === false ? "Not compatible" : "Unavailable";
  }
  if (setting.active !== undefined) {
    return setting.active ? "Active" : setting.enabled ? "Enabled" : "Disabled";
  }
  return setting.enabled ? "Enabled" : "Disabled";
};

const InfoRow: VFC<{ label: string; value: string }> = ({ label, value }) => (
  <div style={statusRowStyle}>
    <div style={infoLabelStyle}>{label}</div>
    <div style={infoValueStyle}>{value}</div>
  </div>
);

const ViewHeader: VFC<{
  title: string;
  subtitle: string;
  backLabel?: string;
  onBack?: () => void;
}> = ({ title, subtitle, backLabel, onBack }) => (
  <PanelSection>
    {onBack && (
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={onBack}>
          {backLabel || "Back"}
        </ButtonItem>
      </PanelSectionRow>
    )}
    <PanelSectionRow>
      <div style={cardStyle}>
        <div style={viewTitleStyle}>{title}</div>
        <div style={subtextStyle}>{subtitle}</div>
      </div>
    </PanelSectionRow>
  </PanelSection>
);

const DashboardView: VFC<{
  data: DashboardState | null;
  loading: boolean;
  busyKey: string | null;
  onRefresh: () => Promise<void>;
  onOpenOptimizations: () => void;
  onOpenInformation: () => void;
}> = ({
  data,
  loading,
  busyKey,
  onRefresh,
  onOpenOptimizations,
  onOpenInformation,
}) => {
  const fpsPresets = data?.fps_limit.presets?.length
    ? data.fps_limit.presets
    : [30, 40, 60, 0];

  const handlePerformanceProfile = async (profileId: string, label: string) => {
    const success = await setPerformanceProfile(profileId);
    toaster.toast({
      title: PLUGIN_NAME,
      body: success ? `${label} SteamOS profile applied` : "Could not apply this SteamOS profile",
    });
    await onRefresh();
  };

  const handleBoost = async (enabled: boolean) => {
    const success = await setCpuBoostEnabled(enabled);
    toaster.toast({
      title: PLUGIN_NAME,
      body: success
        ? `CPU Boost ${enabled ? "enabled" : "disabled"}`
        : "Could not change CPU Boost",
    });
    await onRefresh();
  };

  const handleSmt = async (enabled: boolean) => {
    const success = await setSmtEnabled(enabled);
    toaster.toast({
      title: PLUGIN_NAME,
      body: success
        ? `SMT ${enabled ? "enabled" : "disabled"}`
        : "Could not change SMT",
    });
    await onRefresh();
  };

  const handleChargeLimit = async (enabled: boolean) => {
    const success = await setChargeLimitEnabled(enabled);
    toaster.toast({
      title: PLUGIN_NAME,
      body: success
        ? `Charge limit ${enabled ? "enabled at 80%" : "disabled"}`
        : "Could not change the charge limit",
    });
    await onRefresh();
  };

  const handleSync = async (key: "vrr" | "vsync", enabled: boolean) => {
    const success = await setDisplaySyncSetting(key, enabled);
    toaster.toast({
      title: PLUGIN_NAME,
      body: success
        ? `${key === "vrr" ? "VRR" : "V-Sync"} ${enabled ? "enabled" : "disabled"}`
        : `Could not change ${key === "vrr" ? "VRR" : "V-Sync"}`,
    });
    await onRefresh();
  };

  const commitFpsLimit = async (value: number) => {
    const success = await setFpsLimit(value);
    toaster.toast({
      title: PLUGIN_NAME,
      body: success
        ? `Max framerate: ${formatFpsLabel(value)}`
        : "Could not change the max framerate",
    });
    await onRefresh();
  };

  const handleRgbToggle = async (enabled: boolean) => {
    const success = await setRgbEnabled(enabled);
    toaster.toast({
      title: PLUGIN_NAME,
      body: success
        ? `RGB ${enabled ? "enabled" : "disabled"}`
        : "Could not change RGB",
    });
    await onRefresh();
  };

  const handleRgbColor = async (color: string) => {
    const success = await setRgbColor(color);
    toaster.toast({
      title: PLUGIN_NAME,
      body: success ? `RGB color: ${color}` : "Could not change the RGB color",
    });
    await onRefresh();
  };

  if (loading || !data) {
    return (
      <PanelSection title="Dashboard">
        <PanelSectionRow>
          <div style={{ ...cardStyle, ...subtextStyle }}>Loading dashboard...</div>
        </PanelSectionRow>
      </PanelSection>
    );
  }

  return (
    <PanelSection title="Dashboard">
      <PanelSectionRow>
        <div style={cardStyle}>
          <div style={viewTitleStyle}>Performance Modes</div>
          <div style={subtextStyle}>
            Choose the handheld's overall behavior directly.
          </div>
        </div>
      </PanelSectionRow>

      {!data.profiles_available && (
        <PanelSectionRow>
          <div style={{ ...cardStyle, ...subtextStyle }}>{data.profiles_status}</div>
        </PanelSectionRow>
      )}

      {data.performance_modes.map((mode) => (
        <PanelSectionRow key={mode.id}>
          <ButtonItem
            layout="below"
            onClick={() => handlePerformanceProfile(mode.native_id, mode.label)}
            disabled={!mode.available || busyKey !== null}
          >
            <div style={modeButtonStyle(mode.active, !mode.available || busyKey !== null)}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: "12px",
                }}
              >
                <div style={{ color: mode.active ? "#0f172a" : "#ffffff", fontWeight: 800 }}>
                  {mode.label}
                </div>
                <div
                  style={{
                    color: mode.active ? "#0f172a" : "#94a3b8",
                    fontSize: "12px",
                    fontWeight: 700,
                  }}
                >
                  {mode.active ? "Active" : "SteamOS native"}
                </div>
              </div>
              <div
                style={{
                  color: mode.active ? "rgba(15,23,42,0.85)" : "#cbd5e1",
                  fontSize: "12px",
                  marginTop: "6px",
                }}
              >
                {mode.available ? mode.description : "Mode unavailable on this system"}
              </div>
            </div>
          </ButtonItem>
        </PanelSectionRow>
      ))}

      <PanelSectionRow>
        <ToggleField
          label={formatToggleLabel("CPU Boost", data.cpu_boost)}
          description={data.cpu_boost.details}
          checked={data.cpu_boost.enabled}
          disabled={!data.cpu_boost.available || busyKey !== null}
          onChange={handleBoost}
        />
      </PanelSectionRow>

      <PanelSectionRow>
        <ToggleField
          label={formatToggleLabel("SMT", data.smt)}
          description={data.smt.details}
          checked={data.smt.enabled}
          disabled={!data.smt.available || busyKey !== null}
          onChange={handleSmt}
        />
      </PanelSectionRow>

      <PanelSectionRow>
        <ToggleField
          label={`Charge limit: ${
            data.charge_limit.enabled ? `${data.charge_limit.limit}%` : "disabled"
          }`}
          description={data.charge_limit.details}
          checked={data.charge_limit.enabled}
          disabled={!data.charge_limit.available || busyKey !== null}
          onChange={handleChargeLimit}
        />
      </PanelSectionRow>

      {data.rgb.available && (
        <div>
          <PanelSectionRow>
            <ToggleField
              label={`RGB: ${data.rgb.enabled ? "enabled" : "disabled"}`}
              description={data.rgb.details}
              checked={data.rgb.enabled}
              disabled={!data.rgb.available || busyKey !== null}
              onChange={handleRgbToggle}
            />
          </PanelSectionRow>
          {data.rgb.enabled && (
            <PanelSectionRow>
              <div style={presetGridStyle}>
                {(data.rgb.presets?.length ? data.rgb.presets : RGB_PRESETS).map((color) => (
                  <ButtonItem
                    key={color}
                    layout="below"
                    disabled={!data.rgb.available || busyKey !== null}
                    onClick={() => handleRgbColor(color)}
                  >
                    <div
                      style={{
                        ...presetButtonStyle(data.rgb.color === color),
                        background: color,
                        color: color === "#FFFFFF" ? "#0f172a" : "#ffffff",
                      }}
                    >
                      {color.replace("#", "")}
                    </div>
                  </ButtonItem>
                ))}
              </div>
            </PanelSectionRow>
          )}
        </div>
      )}

      <PanelSectionRow>
        <ToggleField
          label={`VRR: ${formatDisplayStatus(data.vrr).toLowerCase()}`}
          description={
            data.vrr.available
              ? data.vrr.active
                ? "VRR currently active"
                : data.vrr.details || data.vrr.status
              : data.vrr.status || data.vrr.details
          }
          checked={data.vrr.enabled}
          disabled={!data.vrr.available || busyKey !== null}
          onChange={(enabled: boolean) => handleSync("vrr", enabled)}
        />
      </PanelSectionRow>

      <PanelSectionRow>
        <ToggleField
          label={`V-Sync: ${formatDisplayStatus(data.vsync).toLowerCase()}`}
          description={
            data.vsync.available
              ? data.vsync.details || data.vsync.status
              : data.vsync.status || data.vsync.details
          }
          checked={data.vsync.enabled}
          disabled={!data.vsync.available || busyKey !== null}
          onChange={(enabled: boolean) => handleSync("vsync", enabled)}
        />
      </PanelSectionRow>

      <PanelSectionRow>
        <div style={cardStyle}>
          <div style={viewTitleStyle}>Max Framerate</div>
          <div style={subtextStyle}>{data.fps_limit.details}</div>
        </div>
      </PanelSectionRow>
      <PanelSectionRow>
        <div style={presetGridStyle}>
          {fpsPresets.map((preset) => (
            <ButtonItem
              key={preset}
              layout="below"
              disabled={!data.fps_limit.available || busyKey !== null}
              onClick={() => commitFpsLimit(preset)}
            >
              <div style={presetButtonStyle(data.fps_limit.current === preset)}>
                {formatFpsLabel(preset)}
              </div>
            </ButtonItem>
          ))}
        </div>
      </PanelSectionRow>

      <PanelSectionRow>
        <ButtonItem layout="below" onClick={onOpenOptimizations}>
          Optimizations
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={onOpenInformation}>
          Information
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
};

const OptimizationsView: VFC<{
  data: OptimizationData | null;
  loading: boolean;
  busyKey: string | null;
  onBack: () => void;
  onRefresh: () => Promise<void>;
}> = ({ data, loading, busyKey, onBack, onRefresh }) => {
  const handleOptimizationToggle = async (
    optimization: OptimizationState,
    enabled: boolean
  ) => {
    const success = await setOptimizationEnabled(optimization.key, enabled);
    toaster.toast({
      title: PLUGIN_NAME,
      body: success
        ? `${optimization.name} ${enabled ? "enabled" : "disabled"}`
        : `Could not change ${optimization.name}`,
    });
    await onRefresh();
  };

  return (
    <div>
      <ViewHeader
        title="Optimizations"
        subtitle="Optional optimizations that can be disabled, sometimes requiring a reboot."
        onBack={onBack}
      />
      {loading || !data ? (
        <PanelSection>
          <PanelSectionRow>
            <div style={{ ...cardStyle, ...subtextStyle }}>Loading optimizations...</div>
          </PanelSectionRow>
        </PanelSection>
      ) : (
        <PanelSection title="Optimizations">
          {data.states.map((optimization) => (
            <PanelSectionRow key={optimization.key}>
              <ToggleField
                label={`${optimization.name}: ${optimization.status}`}
                description={`${optimization.description} ${optimization.needs_reboot ? "Reboot required. " : ""}${optimization.risk_note}`.trim()}
                checked={optimization.enabled}
                disabled={!optimization.available || busyKey !== null}
                onChange={(enabled: boolean) =>
                  handleOptimizationToggle(optimization, enabled)
                }
              />
            </PanelSectionRow>
          ))}
        </PanelSection>
      )}
    </div>
  );
};

const InformationView: VFC<{
  data: InformationState | null;
  loading: boolean;
  onBack: () => void;
}> = ({ data, loading, onBack }) => {
  return (
    <div>
      <ViewHeader
        title="Information"
        subtitle="Detailed technical status for the handheld and available controls."
        onBack={onBack}
      />
      {loading || !data ? (
        <PanelSection>
          <PanelSectionRow>
            <div style={{ ...cardStyle, ...subtextStyle }}>Loading information...</div>
          </PanelSectionRow>
        </PanelSection>
      ) : (
        <div>
          <PanelSection title="Device">
            <PanelSectionRow>
              <div style={cardStyle}>
                <InfoRow label="Device" value={data.device.friendly_name} />
                <InfoRow label="Vendor" value={data.device.sys_vendor} />
                <InfoRow label="Variant" value={data.device.variant} />
                <InfoRow label="Board" value={data.device.board_name} />
                <InfoRow label="Support" value={data.device.support_level} />
                <InfoRow
                  label="Platform"
                  value={data.device.platform_support_reason || "Unknown"}
                />
                <InfoRow label="SteamOS" value={data.device.steamos_version} />
                <InfoRow label="Kernel" value={data.device.kernel} />
                <InfoRow label="BIOS" value={data.device.bios_version} />
              </div>
            </PanelSectionRow>
          </PanelSection>

          <PanelSection title="Hardware">
            <PanelSectionRow>
              <div style={cardStyle}>
                <InfoRow label="CPU" value={data.device.cpu} />
                <InfoRow label="GPU" value={data.device.gpu} />
                <InfoRow label="RAM" value={data.device.memory_total} />
                <InfoRow
                  label="Temp CPU"
                  value={`${data.temperatures.cpu.toFixed(0)} °C`}
                />
                <InfoRow
                  label="Temp GPU"
                  value={`${data.temperatures.gpu.toFixed(0)} °C`}
                />
                <InfoRow
                  label="GPU Clock"
                  value={`${data.temperatures.gpu_clock.toFixed(0)} MHz`}
                />
              </div>
            </PanelSectionRow>
          </PanelSection>

          <PanelSection title="Battery">
            <PanelSectionRow>
              <div style={cardStyle}>
                <InfoRow
                  label="Status"
                  value={
                    data.battery.present
                      ? `${data.battery.capacity}% (${data.battery.status})`
                      : "Battery not detected"
                  }
                />
                <InfoRow label="Health" value={`${data.battery.health}%`} />
                <InfoRow
                  label="Cycles"
                  value={String(data.battery.cycle_count)}
                />
                <InfoRow
                  label="Temperature"
                  value={
                    data.battery.temperature > 0
                      ? `${data.battery.temperature} °C`
                      : "Unknown"
                  }
                />
                <InfoRow
                  label="Charge limit"
                  value={`${data.battery.charge_limit}%`}
                />
                <InfoRow label="Voltage" value={formatNumber(data.battery.voltage, "V")} />
                <InfoRow label="Current" value={formatNumber(data.battery.current, "A")} />
                <InfoRow
                  label="Design capacity"
                  value={formatNumber(data.battery.design_capacity, "Wh")}
                />
                <InfoRow
                  label="Full capacity"
                  value={formatNumber(data.battery.full_capacity, "Wh")}
                />
                <InfoRow label="Time to empty" value={data.battery.time_to_empty || "Unknown"} />
                <InfoRow label="Time to full" value={data.battery.time_to_full || "Unknown"} />
              </div>
            </PanelSectionRow>
          </PanelSection>

          <PanelSection title="SteamOS / Display">
            <PanelSectionRow>
              <div style={cardStyle}>
                <InfoRow
                  label="Current profile"
                  value={data.performance.current_profile || "Unknown"}
                />
                <InfoRow
                  label="Native profiles"
                  value={data.performance.available_native.join(", ") || "None"}
                />
                <InfoRow
                  label="VRR"
                  value={formatDisplayStatus(data.display.vrr)}
                />
                <InfoRow
                  label="V-Sync"
                  value={formatDisplayStatus(data.display.vsync)}
                />
                <InfoRow
                  label="Max Framerate"
                  value={formatFpsLabel(data.fps_limit.current)}
                />
                <InfoRow
                  label="Current TDP"
                  value={formatNumber(data.temperatures.tdp, "W")}
                />
              </div>
            </PanelSectionRow>
          </PanelSection>

          <PanelSection title="Optimizations">
            <PanelSectionRow>
              <div style={cardStyle}>
                {data.optimizations.map((optimization) => (
                  <div key={optimization.key} style={{ marginBottom: "10px" }}>
                    <div
                      style={{
                        ...statusRowStyle,
                        marginBottom: "2px",
                      }}
                    >
                      <div style={{ color: "#ffffff", fontSize: "12px", fontWeight: 700 }}>
                        {optimization.name}
                      </div>
                      <div
                        style={{
                          color: statusColor(optimization.status),
                          fontSize: "12px",
                          textTransform: "capitalize",
                        }}
                      >
                        {optimization.status}
                      </div>
                    </div>
                    <div style={subtextStyle}>{optimization.description}</div>
                  </div>
                ))}
              </div>
            </PanelSectionRow>
          </PanelSection>

          <PanelSection title="Available Controls">
            <PanelSectionRow>
              <div style={cardStyle}>
                {Object.entries(data.hardware_controls).map(([key, supported]) => (
                  <InfoRow
                    key={key}
                    label={hardwareControlLabels[key] || key}
                    value={supported ? "Available" : "Unavailable"}
                  />
                ))}
              </div>
            </PanelSectionRow>
          </PanelSection>
        </div>
      )}
    </div>
  );
};

const XboxCompanionContent: VFC = () => {
  const [view, setView] = useState<ViewName>("dashboard");
  const [dashboard, setDashboard] = useState<DashboardState | null>(null);
  const [optimizations, setOptimizations] = useState<OptimizationData | null>(null);
  const [information, setInformation] = useState<InformationState | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const refreshDashboard = async (options?: { silent?: boolean }) => {
    const silent = options?.silent ?? false;
    if (!silent) {
      setBusyKey("dashboard");
    }
    try {
      setDashboard(await getDashboardState());
    } catch (error) {
      console.error("Failed to refresh dashboard:", error);
    } finally {
      if (!silent) {
        setBusyKey(null);
      }
      setLoading(false);
    }
  };

  const refreshOptimizations = async () => {
    setBusyKey("optimizations");
    try {
      setOptimizations(await getOptimizationStates());
    } catch (error) {
      console.error("Failed to refresh optimizations:", error);
    } finally {
      setBusyKey(null);
      setLoading(false);
    }
  };

  const refreshInformation = async () => {
    setBusyKey("information");
    try {
      setInformation(await getInformationState());
    } catch (error) {
      console.error("Failed to refresh information:", error);
    } finally {
      setBusyKey(null);
      setLoading(false);
    }
  };

  useEffect(() => {
    if (view === "dashboard") {
      void refreshDashboard();
      const interval = setInterval(() => {
        void refreshDashboard({ silent: true });
      }, 5000);
      return () => clearInterval(interval);
    }

    if (view === "optimizations") {
      void refreshOptimizations();
      return;
    }

    void refreshInformation();
  }, [view]);

  if (view === "optimizations") {
    return (
      <OptimizationsView
        data={optimizations}
        loading={loading}
        busyKey={busyKey}
        onBack={() => setView("dashboard")}
        onRefresh={refreshOptimizations}
      />
    );
  }

  if (view === "information") {
    return (
      <InformationView
        data={information}
        loading={loading}
        onBack={() => setView("dashboard")}
      />
    );
  }

  return (
    <DashboardView
      data={dashboard}
      loading={loading}
      busyKey={busyKey}
      onRefresh={refreshDashboard}
      onOpenOptimizations={() => {
        setLoading(true);
        setView("optimizations");
      }}
      onOpenInformation={() => {
        setLoading(true);
        setView("information");
      }}
    />
  );
};

const XboxCompanionIcon: VFC = () => (
  <svg viewBox="0 0 24 24" fill="currentColor" width="1em" height="1em">
    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" />
  </svg>
);

export default definePlugin(() => {
  console.log("Xbox Companion plugin loaded!");

  return {
    name: "Xbox Companion",
    title: <div className={staticClasses.Title}>Xbox Companion</div>,
    content: <XboxCompanionContent />,
    icon: <XboxCompanionIcon />,
    onDismount() {
      console.log("Xbox Companion plugin unloaded!");
    },
  };
});
