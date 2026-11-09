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
export const updateDailyLog = (id, data) => api.put(`/daily-logs/${id}`, data);
export const lockDailyLog = (id) => api.post(`/daily-logs/${id}/lock`);

// Events (Admin only)
export const createEvent = (logId, data) => api.post(`/daily-logs/${logId}/events`, data);
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

// Animals
export const getAnimals = (params) => api.get('/animals', { params });
export const getAnimal = (id) => api.get(`/animals/${id}`);
export const createAnimal = (data) => api.post('/animals', data);
export const updateAnimal = (id, data) => api.put(`/animals/${id}`, data);
export const transferAnimal = (id, data) => api.post(`/animals/${id}/transfer`, data);
export const bulkImportAnimals = (file) => {
  const formData = new FormData();
  formData.append('file', file);
  return api.post('/animals/bulk-import', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
};
export const downloadAnimalsTemplate = () => `${API_URL}/api/templates/animals`;

// Health Intervals
export const getHealthIntervals = (params) => api.get('/health-intervals', { params });
export const createHealthInterval = (data) => api.post('/health-intervals', data);
export const updateHealthInterval = (id, data) => api.put(`/health-intervals/${id}`, data);
export const deleteHealthInterval = (id) => api.delete(`/health-intervals/${id}`);

// Farm Health Events
export const getFarmHealthEvents = (params) => api.get('/farm-health', { params });
export const getFarmHealthEventById = (id) => api.get(`/farm-health/${id}`);
export const createFarmHealthEvent = (data) => api.post('/farm-health', data);
export const updateFarmHealthEvent = (id, data) => api.put(`/farm-health/${id}`, data);
export const deleteFarmHealthEvent = (id) => api.delete(`/farm-health/${id}`);
export const getLastEvents = (params) => api.get('/farm-health/last-events', { params });
export const getUpcomingHealthEvents = (params) => api.get('/farm-health/upcoming', { params });
export const getProductSuggestions = (params) => api.get('/farm-health/product-suggestions', { params });

// Vaccine Types
export const getVaccineTypes = (species) => api.get('/vaccine-types', { params: species ? { species } : {} });
export const createVaccineType = (data) => api.post('/vaccine-types', data);
export const updateVaccineType = (id, data) => api.put(`/vaccine-types/${id}`, data);
export const deleteVaccineType = (id) => api.delete(`/vaccine-types/${id}`);
export const getLastVaccinations = () => api.get('/farm-health-events/last-vaccinations');

// Reproduction (backend: docs/decisions/0008)
export const getReproductionAnalytics = (locationId, year) =>
  api.get('/analytics/reproduction', { params: { location_id: locationId, year } });
export const getReproductiveCycles = (params) => api.get('/reproductive-cycles', { params });
export const getReproductiveCycle = (id) => api.get(`/reproductive-cycles/${id}`);
export const createReproductiveCycle = (data) => api.post('/reproductive-cycles', data);
export const updateReproductiveCycle = (id, data) => api.put(`/reproductive-cycles/${id}`, data);
export const getBullAssignments = (params) => api.get('/bull-assignments', { params });
export const createBullAssignment = (data) => api.post('/bull-assignments', data);
export const updateBullAssignment = (id, data) => api.put(`/bull-assignments/${id}`, data);
export const getBCSRecords = (params) => api.get('/bcs-records', { params });
export const createBCSRecord = (data) => api.post('/bcs-records', data);
export const searchAnimals = (params) => api.get('/animals', { params });

// Animal profile (backend: docs/decisions/0008)
export const getAnimalDetail = (id) => api.get(`/animals/${id}`);
export const getAnimalTimeline = (id) => api.get(`/animals/${id}/timeline`);
export const getAnimalReproductiveHistory = (id) => api.get(`/animals/${id}/reproductive-history`);
export const getAnimalPhotos = (id) => api.get(`/animals/${id}/photos`);
export const uploadAnimalPhoto = (id, formData) =>
  api.post(`/animals/${id}/photos`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
export const updateAnimalPhoto = (id, photoId, data) => api.put(`/animals/${id}/photos/${photoId}`, data);
export const deleteAnimalPhoto = (id, photoId) => api.delete(`/animals/${id}/photos/${photoId}`);
export const getAnimalNotes = (id) => api.get(`/animals/${id}/notes`);
export const createAnimalNote = (id, data) => api.post(`/animals/${id}/notes`, data);
export const updateAnimalNote = (id, noteId, data) => api.put(`/animals/${id}/notes/${noteId}`, data);
export const deleteAnimalNote = (id, noteId) => api.delete(`/animals/${id}/notes/${noteId}`);
export const getAnimalBCSHistory = (id) => api.get('/bcs-records', { params: { animal_id: id } });

// Animal register: movement history + reconciliation (backend: docs/decisions/0009)
export const getAnimalLocationHistory = (id) =>
  api.get(`/animals/${id}/location-history`);

export const getRegisterReconciliation = () =>
  api.get('/animals/register-reconciliation');

// Temp tags (backend: docs/decisions/0009 follow-up)
export const replaceAnimalTag = (id, newTagNumber) =>
  api.post(`/animals/${id}/replace-tag`, { new_tag_number: newTagNumber });

export default api;

// Additional animal identifiers and baseline import
export const getAnimalIdentifiers = (animalId) => api.get(`/animals/${animalId}/identifiers`);
export const createAnimalIdentifier = (animalId, data) => api.post(`/animals/${animalId}/identifiers`, data);
export const updateAnimalIdentifier = (animalId, identifierId, data) =>
  api.put(`/animals/${animalId}/identifiers/${identifierId}`, data);
export const deleteAnimalIdentifier = (animalId, identifierId) =>
  api.delete(`/animals/${animalId}/identifiers/${identifierId}`);
export const lookupAnimalByIdentifier = (idType, idValue) =>
  api.get('/animals/lookup-by-id', { params: { id_type: idType, id_value: idValue } });
export const importAnimalIdentifiers = (file) => {
  const formData = new FormData();
  formData.append('file', file);
  return api.post('/admin/import/animal-identifiers', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
};

// Standalone reproductive events
export const getReproductiveSummary = (animalId) => api.get(`/animals/${animalId}/reproductive-summary`);
export const listReproductiveEvents = (animalId) => api.get(`/animals/${animalId}/reproductive-events`);
export const createReproductiveEvent = (animalId, data) => api.post(`/animals/${animalId}/reproductive-events`, data);
export const listRepeatBreeders = (params) => api.get('/animals/repeat-breeders', { params });
export const syncReproductiveStatus = () => api.post('/admin/tasks/sync-reproductive-status');
