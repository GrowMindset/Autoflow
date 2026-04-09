import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Mail, Lock, User as UserIcon, LogIn } from 'lucide-react';
import { authService } from '../services/authService';
import toast from 'react-hot-toast';

const Signup: React.FC = () => {
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !username || !password) {
      toast.error('Please fill in all fields');
      return;
    }

    if (password.length < 8) {
      toast.error('Password must be at least 8 characters');
      return;
    }

    setIsLoading(true);
    try {
      await authService.signup({ email, username, password });
      toast.success('Account created successfully! Please sign in.');
      navigate('/login');
    } catch (error: any) {
      console.error('Signup failed:', error);
      // api interceptor handles toast
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-sm bg-white rounded-2xl shadow-sm border border-slate-200 p-8">
        <div className="flex flex-col items-center mb-10 text-center">
          <div className="w-12 h-12 bg-emerald-600 rounded-xl flex items-center justify-center text-white mb-4 shadow-md shadow-emerald-200">
            <LogIn size={24} className="rotate-180" />
          </div>
          <h1 className="text-2xl font-bold text-slate-900">Create Account</h1>
          <p className="text-slate-500 text-sm mt-1">Join the Autoflow engine</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="space-y-2">
            <label className="text-sm font-semibold text-slate-700">Username</label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                <UserIcon size={18} />
              </div>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full bg-white border border-slate-300 text-slate-900 pl-10 pr-4 py-2.5 rounded-lg outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100 transition-all text-sm"
                placeholder="johndoe"
                required
              />
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-semibold text-slate-700">Email Address</label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                <Mail size={18} />
              </div>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full bg-white border border-slate-300 text-slate-900 pl-10 pr-4 py-2.5 rounded-lg outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100 transition-all text-sm"
                placeholder="name@example.com"
                required
              />
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-semibold text-slate-700">Password</label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                <Lock size={18} />
              </div>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full bg-white border border-slate-300 text-slate-900 pl-10 pr-4 py-2.5 rounded-lg outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100 transition-all text-sm"
                placeholder="••••••••"
                required
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-3 rounded-lg shadow-sm active:scale-[0.98] transition-all disabled:opacity-70 disabled:active:scale-100 mt-2"
          >
            {isLoading ? "Creating account..." : "Create Account"}
          </button>
        </form>

        <div className="mt-8 pt-6 border-t border-slate-100 text-center">
          <p className="text-sm text-slate-600">
            Already have an account? <Link to="/login" className="text-emerald-600 hover:text-emerald-700 font-bold ml-1 transition-colors">Sign in</Link>
          </p>
        </div>
      </div>
    </div>
  );
};

export default Signup;
