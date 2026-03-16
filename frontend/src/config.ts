const isProd = import.meta.env.PROD;
export const API_BASE_URL = import.meta.env.VITE_API_URL || (isProd ? '' : 'http://localhost:8000');
