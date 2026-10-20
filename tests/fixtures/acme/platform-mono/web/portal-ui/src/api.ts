export const api = (p: string) => fetch(`${import.meta.env.VITE_API_URL}${p}`)
