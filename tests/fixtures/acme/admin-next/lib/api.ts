export const api = (path: string) => fetch(`${process.env.NEXT_PUBLIC_API_URL}${path}`)
