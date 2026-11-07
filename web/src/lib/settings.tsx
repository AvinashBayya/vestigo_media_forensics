import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { DEFAULT_OPTIONS, getSettings } from "../api/client";
import type { EditableSettings } from "../api/types";

export const DEFAULT_VIDEO_OPTIONS = {
  metadata: true,
  c2pa: true,
  location_clues: true,
  scene_detection: true,
  keyframe_ocr: false, // off by default (M3-3)
  duplicate_search: true,
} as const;

export const DEFAULT_AUDIO_OPTIONS = {
  metadata: true,
  c2pa: true,
  location_clues: true,
  duplicate_search: true,
} as const;

export const DEFAULT_SETTINGS: EditableSettings = {
  default_analysis_options: DEFAULT_OPTIONS,
  default_video_analysis_options: { ...DEFAULT_VIDEO_OPTIONS },
  default_audio_analysis_options: { ...DEFAULT_AUDIO_OPTIONS },
  library_page_size: 25,
  auto_analyze_after_upload: true,
  enabled_search_providers: [],
  enable_external_map_links: false,
};

interface SettingsContextValue {
  settings: EditableSettings;
  /** True once the saved settings were loaded, or loading failed and the defaults apply. */
  loaded: boolean;
  setSettings: (settings: EditableSettings) => void;
}

const SettingsContext = createContext<SettingsContextValue>({
  settings: DEFAULT_SETTINGS,
  loaded: true,
  setSettings: () => undefined,
});

export function useSettings(): SettingsContextValue {
  return useContext(SettingsContext);
}

/** Loads the analyst's editable settings once. If they cannot be loaded, the defaults apply. */
export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettingsState] = useState<EditableSettings>(DEFAULT_SETTINGS);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let current = true;
    getSettings()
      .then((response) => current && setSettingsState(response.editable))
      .catch(() => undefined)
      .finally(() => current && setLoaded(true));
    return () => {
      current = false;
    };
  }, []);

  const setSettings = useCallback((next: EditableSettings) => setSettingsState(next), []);
  const value = useMemo(() => ({ settings, loaded, setSettings }), [settings, loaded, setSettings]);
  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}
