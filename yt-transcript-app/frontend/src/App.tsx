import { useState } from 'react';
import { Video } from './types/video';
import { useVideos, useTranscript } from './hooks/useVideos';
import { VideoCard } from './components/VideoCard';
import { SearchBar } from './components/SearchBar';
import { TranscriptViewer } from './components/TranscriptViewer';
import { Modal } from './components/Modal';
import { LoadingSpinner } from './components/LoadingSpinner';

function formatLastUpdated(dateStr: string | null): string {
  if (!dateStr) return 'Never';
  const date = new Date(dateStr);
  return date.toLocaleString();
}

export default function App() {
  const {
    videos,
    isLoading,
    error,
    lastUpdated,
    searchQuery,
    setSearchQuery,
    refresh,
  } = useVideos();

  const [selectedVideo, setSelectedVideo] = useState<Video | null>(null);
  const [transcriptView, setTranscriptView] = useState<'segmented' | 'full'>('segmented');
  const { transcript, isLoading: transcriptLoading, error: transcriptError } = useTranscript(
    selectedVideo?.id || null
  );

  return (
    <div className="min-h-screen bg-light-50">
      {/* Background gradient */}
      <div className="fixed inset-0 bg-gradient-to-br from-accent-purple/5 via-transparent to-accent-blue/5 pointer-events-none" />

      <div className="relative z-10">
        {/* Header */}
        <header className="sticky top-0 z-40 bg-white/90 backdrop-blur-lg border-b border-light-300 shadow-sm">
          <div className="max-w-7xl mx-auto px-4 py-4">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div>
                <h1 className="text-2xl font-bold bg-gradient-to-r from-accent-purple to-accent-blue bg-clip-text text-transparent">
                  bycloudAI Transcripts
                </h1>
                <p className="text-sm text-gray-500 mt-1">
                  Last updated: {formatLastUpdated(lastUpdated)}
                </p>
              </div>

              <div className="flex items-center gap-3">
                <button
                  onClick={refresh}
                  disabled={isLoading}
                  className="flex items-center gap-2 px-4 py-2 bg-accent-purple hover:bg-accent-purple/80
                             disabled:bg-accent-purple/50 text-white rounded-lg transition-all duration-200
                             shadow-lg shadow-accent-purple/20"
                >
                  <svg className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                          d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  Refresh
                </button>
              </div>
            </div>

            {/* Search */}
            <div className="mt-4">
              <SearchBar
                value={searchQuery}
                onChange={setSearchQuery}
                placeholder="Search by video title..."
              />
            </div>
          </div>
        </header>

        {/* Main Content */}
        <main className="max-w-7xl mx-auto px-4 py-8">
          {/* Error State */}
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-8">
              <p className="text-red-600">{error}</p>
            </div>
          )}

          {/* Loading State */}
          {isLoading && videos.length === 0 && (
            <div className="flex items-center justify-center min-h-[50vh]">
              <LoadingSpinner size="lg" message="Loading videos..." />
            </div>
          )}

          {/* Video Grid */}
          {!isLoading && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
              {videos.map(video => (
                <VideoCard
                  key={video.id}
                  video={video}
                  onClick={() => setSelectedVideo(video)}
                />
              ))}
            </div>
          )}

          {/* Empty State */}
          {!isLoading && videos.length === 0 && !error && (
            <div className="flex flex-col items-center justify-center min-h-[50vh] text-center">
              <svg className="w-16 h-16 text-gray-600 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                      d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
              <h3 className="text-xl font-semibold text-gray-400">No videos found</h3>
              <p className="text-gray-600 mt-2">Try adjusting your search or refresh the feed</p>
            </div>
          )}
        </main>
      </div>

      {/* Transcript Modal */}
      <Modal
        isOpen={!!selectedVideo}
        onClose={() => setSelectedVideo(null)}
        title={selectedVideo?.title || ''}
      >
        {transcriptLoading && (
          <div className="flex items-center justify-center py-12">
            <LoadingSpinner message="Loading transcript..." />
          </div>
        )}

        {transcriptError && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-4">
            <p className="text-red-600">{transcriptError}</p>
          </div>
        )}

        {transcript && !transcriptLoading && (
          <div>
            {/* View toggle */}
            <div className="flex items-center justify-between mb-4">
              <p className="text-sm text-gray-500">
                {transcript.lines.length} segments
              </p>
              <div className="flex bg-light-200 rounded-lg p-1">
                <button
                  onClick={() => setTranscriptView('segmented')}
                  className={`px-3 py-1 text-sm rounded-md transition-colors ${
                    transcriptView === 'segmented'
                      ? 'bg-accent-purple text-white'
                      : 'text-gray-500 hover:text-gray-800'
                  }`}
                >
                  Segmented
                </button>
                <button
                  onClick={() => setTranscriptView('full')}
                  className={`px-3 py-1 text-sm rounded-md transition-colors ${
                    transcriptView === 'full'
                      ? 'bg-accent-purple text-white'
                      : 'text-gray-500 hover:text-gray-800'
                  }`}
                >
                  Full Text
                </button>
              </div>
            </div>
            <TranscriptViewer lines={transcript.lines} viewMode={transcriptView} />
          </div>
        )}
      </Modal>
    </div>
  );
}