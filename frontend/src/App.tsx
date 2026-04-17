import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import MainLayout from './components/layout/MainLayout';
import Login from './pages/Login';
import Signup from './pages/Signup';
import WorkflowFormPage from './pages/WorkflowFormPage';
import GoogleOAuthCallback from './pages/GoogleOAuthCallback';
import LinkedInOAuthCallback from './pages/LinkedInOAuthCallback';
import ProtectedRoute from './components/auth/ProtectedRoute';
import { Toaster } from 'react-hot-toast';
import { ThemeProvider } from './context/ThemeContext';

const App: React.FC = () => {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <Routes>
          {/* Public Routes */}
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />

          {/* Protected Routes */}
          <Route element={<ProtectedRoute />}>
            <Route path="/" element={<MainLayout />} />
            <Route path="/app/*" element={<MainLayout />} />
            <Route path="/app/forms/:workflowId" element={<WorkflowFormPage />} />
            <Route path="/app/oauth/google/callback" element={<GoogleOAuthCallback />} />
            <Route path="/app/oauth/linkedin/callback" element={<LinkedInOAuthCallback />} />
          </Route>

          {/* Fallback */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        <Toaster position="bottom-right" />
      </BrowserRouter>
    </ThemeProvider>
  );
};

export default App;
