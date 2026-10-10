export interface Memory {
  id: string;
  user_id: string;
  lat: number;
  lon: number;
  title: string | null;
  description: string | null;
  media_url: string;
  media_type: 'image' | 'video';
  visibility: 'public' | 'friends' | 'private';
  unlock_radius_m: number;
  created_at: string;
  updated_at: string;
}

export interface CreateMemoryRequest {
  lat: number;
  lon: number;
  title?: string;
  description?: string;
  media_url: string;
  media_type: 'image' | 'video';
  visibility: 'public' | 'friends' | 'private';
  unlock_radius_m: number;
}

export interface Favorite {
  id: string;
  user_id: string;
  kind: 'station' | 'line' | 'place';
  ref_id: string;
  label: string | null;
  created_at: string;
}

export interface LocationShare {
  id: string;
  user_id: string;
  lat: number;
  lon: number;
  accuracy_m: number | null;
  note: string | null;
  is_active: boolean;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
}
