// A device counts as "online"/"fresh" if its most recent measurement
// arrived within this window. Shared so every component agrees on one number
export const FRESH_MS = 120_000
