const base = import.meta.env.VITE_ORDERS_URL

export const fetchOrders = () => fetch(`${base}/orders`).then((r) => r.json())
