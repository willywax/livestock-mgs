import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { Toaster } from "./components/ui/sonner";
import { Layout } from "./components/Layout";

// Pages
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Locations from "./pages/Locations";
import LocationDetail from "./pages/LocationDetail";
import DailyLogs from "./pages/DailyLogs";
import NewDailyLog from "./pages/NewDailyLog";
import DailyLogDetail from "./pages/DailyLogDetail";
import OpeningBalances from "./pages/OpeningBalances";
import Reports from "./pages/Reports";
import Users from "./pages/Users";
import Settings from "./pages/Settings";
import Animals from "./pages/Animals";
import FarmHealth from "./pages/FarmHealth";
import RegistrySync from "./pages/RegistrySync";

// Protected Route Component
const ProtectedRoute = ({ children, allowedRoles }) => {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return <Navigate to="/" replace />;
  }

  return <Layout>{children}</Layout>;
};

// Public Route Component (redirect if logged in)
const PublicRoute = ({ children }) => {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    );
  }

  if (user) {
    return <Navigate to="/" replace />;
  }

  return children;
};

function AppRoutes() {
  return (
    <Routes>
      {/* Public Routes */}
      <Route
        path="/login"
        element={
          <PublicRoute>
            <Login />
          </PublicRoute>
        }
      />

      {/* Protected Routes */}
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Dashboard />
          </ProtectedRoute>
        }
      />

      <Route
        path="/locations"
        element={
          <ProtectedRoute>
            <Locations />
          </ProtectedRoute>
        }
      />

      <Route
        path="/locations/:id"
        element={
          <ProtectedRoute>
            <LocationDetail />
          </ProtectedRoute>
        }
      />

      <Route
        path="/animals"
        element={
          <ProtectedRoute>
            <Animals />
          </ProtectedRoute>
        }
      />

      <Route
        path="/farm-health"
        element={
          <ProtectedRoute>
            <FarmHealth />
          </ProtectedRoute>
        }
      />

      <Route
        path="/daily-logs"
        element={
          <ProtectedRoute>
            <DailyLogs />
          </ProtectedRoute>
        }
      />

      <Route
        path="/daily-logs/new"
        element={
          <ProtectedRoute allowedRoles={["admin", "data_entry"]}>
            <NewDailyLog />
          </ProtectedRoute>
        }
      />

      <Route
        path="/daily-logs/:id"
        element={
          <ProtectedRoute>
            <DailyLogDetail />
          </ProtectedRoute>
        }
      />

      <Route
        path="/opening-balances"
        element={
          <ProtectedRoute allowedRoles={["admin"]}>
            <OpeningBalances />
          </ProtectedRoute>
        }
      />

      <Route
        path="/reports"
        element={
          <ProtectedRoute>
            <Reports />
          </ProtectedRoute>
        }
      />

      <Route
        path="/admin/users"
        element={
          <ProtectedRoute allowedRoles={["admin"]}>
            <Users />
          </ProtectedRoute>
        }
      />

      <Route
        path="/settings"
        element={
          <ProtectedRoute allowedRoles={["admin"]}>
            <Settings />
          </ProtectedRoute>
        }
      />

      <Route
        path="/admin/registry-sync"
        element={
          <ProtectedRoute allowedRoles={["admin"]}>
            <RegistrySync />
          </ProtectedRoute>
        }
      />

      {/* Catch all - redirect to dashboard */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
        <Toaster position="top-right" richColors />
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
