const endpoint = import.meta.env.VITE_ANALYTICS_URL

export const track = (event: string) => fetch(endpoint, { method: "POST", body: event })
