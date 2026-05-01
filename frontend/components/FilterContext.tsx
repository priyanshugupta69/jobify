"use client";

import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

interface FilterState {
  site: string | null;
  setSite: (s: string | null) => void;
  toggleSite: (s: string) => void;
}

const FilterCtx = createContext<FilterState>({
  site: null,
  setSite: () => {},
  toggleSite: () => {},
});

export function FilterProvider({ children }: { children: ReactNode }) {
  const [site, setSite] = useState<string | null>(null);

  const toggleSite = useCallback((s: string) => {
    setSite((prev) => (prev?.toLowerCase() === s.toLowerCase() ? null : s));
  }, []);

  return (
    <FilterCtx.Provider value={{ site, setSite, toggleSite }}>
      {children}
    </FilterCtx.Provider>
  );
}

export const useFilters = () => useContext(FilterCtx);
