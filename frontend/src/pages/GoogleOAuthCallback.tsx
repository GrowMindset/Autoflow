import React, { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import toast from 'react-hot-toast';

import { CredentialItem, credentialService } from '../services/credentialService';

const inflightExchangeByState = new Map<string, Promise<CredentialItem>>();

const GoogleOAuthCallback: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const startedRef = useRef(false);
  const [statusText, setStatusText] = useState('Completing Google OAuth connection...');

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    const error = searchParams.get('error');
    const errorDescription = searchParams.get('error_description');
    const code = searchParams.get('code') || '';
    const state = searchParams.get('state') || '';

    if (error) {
      const message = errorDescription || error;
      setStatusText(`Google OAuth failed: ${message}`);
      toast.error(`Google OAuth failed: ${message}`);
      window.setTimeout(() => navigate('/', { replace: true }), 1200);
      return;
    }

    if (!code || !state) {
      setStatusText('Missing OAuth code/state. Please retry connection.');
      toast.error('Google OAuth callback is missing required data.');
      window.setTimeout(() => navigate('/', { replace: true }), 1200);
      return;
    }

    const redirectUri = `${window.location.origin}/app/oauth/google/callback`;
    const exchangeKey = `${code}:${state}:${redirectUri}`;
    let exchangePromise = inflightExchangeByState.get(exchangeKey);
    if (!exchangePromise) {
      exchangePromise = credentialService.exchangeGoogleOAuth({ code, state, redirect_uri: redirectUri });
      inflightExchangeByState.set(exchangeKey, exchangePromise);
    }

    void exchangePromise
      .then((credential: CredentialItem) => {
        setStatusText(`Google account connected for ${credential.app_name}. Redirecting...`);
        toast.success(`Google ${credential.app_name} credential connected.`);
        window.setTimeout(() => navigate('/', { replace: true }), 700);
      })
      .catch((err: any) => {
        const detail = err?.response?.data?.detail || err?.message || 'Unknown error';
        setStatusText(`Google OAuth exchange failed: ${detail}`);
        toast.error(`Google OAuth exchange failed: ${detail}`);
        window.setTimeout(() => navigate('/', { replace: true }), 1500);
      })
      .finally(() => {
        inflightExchangeByState.delete(exchangeKey);
      });
  }, [navigate, searchParams]);

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-slate-50 dark:bg-slate-900 px-6">
      <div className="max-w-lg w-full rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-sm p-6 text-center">
        <div className="w-12 h-12 mx-auto mb-4 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">{statusText}</p>
      </div>
    </div>
  );
};

export default GoogleOAuthCallback;
