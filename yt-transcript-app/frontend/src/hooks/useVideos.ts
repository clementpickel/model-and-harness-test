import { useState, useEffect, useCallback } from 'react';
import { Video, TranscriptResponse } from '../types/video';
import { fetchVideos, fetchTranscript, refreshVideos } from '../api/client';

export function useVideos() {
  const [videos, setVideos] = useState<Video[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const loadVideos = useCallback(async () => {
    try {
      setError(null);
      const data = await fetchVideos();
      setVideos(data.videos);
      setLastUpdated(data.last_updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load videos');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const triggerRefresh = useCallback(async () => {
    setIsLoading(true);
    try {
      await refreshVideos();
      await loadVideos();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to refresh');
    }
  }, [loadVideos]);

  useEffect(() => {
    loadVideos();
  }, [loadVideos]);

  // Auto-refresh every 5 minutes
  useEffect(() => {
    const interval = setInterval(loadVideos, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [loadVideos]);

  const filteredVideos = videos.filter(video =>
    video.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return {
    videos: filteredVideos,
    isLoading,
    error,
    lastUpdated,
    searchQuery,
    setSearchQuery,
    refresh: triggerRefresh,
    reload: loadVideos,
  };
}

export function useTranscript(videoId: string | null) {
  const [transcript, setTranscript] = useState<TranscriptResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!videoId) {
      setTranscript(null);
      return;
    }

    let cancelled = false;
    setIsLoading(true);
    setError(null);

    fetchTranscript(videoId)
      .then(data => {
        if (!cancelled) {
          setTranscript(data);
        }
      })
      .catch(err => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load transcript');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [videoId]);

  return { transcript, isLoading, error };
}