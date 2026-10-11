import { writable, derived } from 'svelte/store';

export interface User {
  id: string;
  email: string;
  display_name: string | null;
  created_at: string;
}

export interface AuthResponse {
  token: string;
  user: User;
}

const stored = typeof localStorage !== 'undefined' ? localStorage.getItem('bledi_token') : null;
const storedUser = typeof localStorage !== 'undefined' ? localStorage.getItem('bledi_user') : null;

export const token = writable<string | null>(stored);
export const user = writable<User | null>(storedUser ? JSON.parse(storedUser) : null);

export const isAuthenticated = derived(token, ($token) => !!$token);

token.subscribe((v) => {
  if (typeof localStorage !== 'undefined') {
    if (v) localStorage.setItem('bledi_token', v);
    else localStorage.removeItem('bledi_token');
  }
});

user.subscribe((v) => {
  if (typeof localStorage !== 'undefined') {
    if (v) localStorage.setItem('bledi_user', JSON.stringify(v));
    else localStorage.removeItem('bledi_user');
  }
});

export async function login(email: string, password: string): Promise<void> {
  const res = await fetch('/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password })
  });
  if (!res.ok) throw new Error((await res.json()).error || 'Login failed');
  const data: AuthResponse = await res.json();
  token.set(data.token);
  user.set(data.user);
}

export async function register(email: string, password: string, displayName?: string): Promise<void> {
  const res = await fetch('/api/v1/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, display_name: displayName })
  });
  if (!res.ok) throw new Error((await res.json()).error || 'Registration failed');
  const data: AuthResponse = await res.json();
  token.set(data.token);
  user.set(data.user);
}

export function logout() {
  token.set(null);
  user.set(null);
}

export function authHeaders(): Record<string, string> {
  let t: string | null = null;
  token.subscribe((v) => (t = v))();
  return t ? { Authorization: 'Bearer ' + t } : {};
}
