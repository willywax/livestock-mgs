import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const api = axios.create({
  baseURL: `${API_URL}/api`,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle auth errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// Auth
export const login = (phone, password) => api.post('/auth/login', { phone, password });
export const getMe = () => api.get('/auth/me');

// Users
export const getUsers = () => api.get('/users');
export const createUser = (data) => api.post('/users', data);
export const updateUser = (id, data) => api.put(`/users/${id}`, data);
export const deleteUser = (id) => api.delete(`/users/${id}`);

// Locations
export const getLocations = () => api.get('/locations');
export const getLocation = (id) => api.get(`/locations/${id}`);
export const createLocation = (data) => api.post('/locations', data);
export const updateLocation = (id, data) => api.put(`/locations/${id}`, data);

// Import/Export Templates
export const downloadLocationsTemplate = () => `${API_URL}/api/templates/locations`;
export const downloadOpeningBalancesTemplate = () => `${API_URL}/api/templates/opening-balances`;

export const importLocations = (file) => {
  const formData = new FormData();
  formData.append('file', file);
  return api.post('/import/locations', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  });
};

export const importOpeningBalances = (file) => {
  const formData = new FormData();
  formData.append('file', file);
  return api.post('/import/opening-balances', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  });
};

// Categories
export const getCategories = (species) => api.get('/categories', { params: { species } });

// Diseases
export const getDiseases = (species) => api.get('/diseases', { params: species ? { species } : {} });
export const createDisease = (data) => api.post('/diseases', data);
export const updateDisease = (id, data) => api.put(`/diseases/${id}`, data);
export const deleteDisease = (id) => api.delete(`/diseases/${id}`);

// Opening Balances
export const getOpeningBalances = (params) => api.get('/opening-balances', { params });
export const createOpeningBalance = (data) => api.post('/opening-balances', data);
export const updateOpeningBalance = (id, data) => api.put(`/opening-balances/${id}`, data);

// Daily Logs
export const getDailyLogs = (params) => api.get('/daily-logs', { params });
export const getDailyLog = (id) => api.get(`/daily-logs/${id}`);
export const createDailyLog = (data) => api.post('/daily-logs', data);
export const lockDailyLog = (id) => api.post(`/daily-logs/${id}/lock`);

// Events (Admin only)
export const updateEvent = (id, data) => api.put(`/events/${id}`, data);
export const deleteEvent = (id) => api.delete(`/events/${id}`);

// Stock Levels
export const getStockLevels = (params) => api.get('/stock-levels', { params });

// Dashboard
export const getDashboard = (params) => api.get('/dashboard', { params });

// Reports
export const getDailyReport = (date) => api.get('/reports/daily', { params: { report_date: date } });
export const getRangeReport = (params) => api.get('/reports/range', { params });
export const getAnalyticsReport = (params) => api.get('/reports/analytics', { params });
export const getDetailedReport = (params) => api.get('/reports/detailed', { params });

export default api;
