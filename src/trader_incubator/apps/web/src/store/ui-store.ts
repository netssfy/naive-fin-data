import { create } from 'zustand'

type Transport = 'http' | 'ipc'

type UiState = {
  launchCount: number
  transport: Transport
  incrementLaunchCount: () => void
  setTransport: (transport: Transport) => void
}

export const useUiStore = create<UiState>((set) => ({
  launchCount: 1,
  transport: 'http',
  incrementLaunchCount: () => set((state) => ({ launchCount: state.launchCount + 1 })),
  setTransport: (transport) => set({ transport }),
}))