import { VideoListResponse, TranscriptResponse } from '../types/video';

const API_BASE = '/api';

async function apiClient<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, options);
  if (!res.ok) {
    throw new Error(`API error: ${res.status}`);
  }
  return res.json();
}

export async function fetchVideos(): Promise<VideoListResponse> {
  return apiClient<VideoListResponse>('/videos');
}

export async function fetchTranscript(videoId: string): Promise<TranscriptResponse> {
  return apiClient<TranscriptResponse>(`/videos/${videoId}/transcript`);
}

export async function refreshVideos(): Promise<{ status: string }> {
  return apiClient<{ status: string }>('/refresh', { method: 'POST' });
}