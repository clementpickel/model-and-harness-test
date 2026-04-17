import { Video } from '../types/video';

interface VideoCardProps {
  video: Video;
  onClick: () => void;
}

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '';
  const year = dateStr.substring(0, 4);
  const month = dateStr.substring(4, 6);
  const day = dateStr.substring(6, 8);
  return `${year}-${month}-${day}`;
}

export function VideoCard({ video, onClick }: VideoCardProps) {
  return (
    <div
      onClick={onClick}
      className="group relative bg-white rounded-xl overflow-hidden cursor-pointer
                 transform transition-all duration-300 hover:scale-105
                 border border-light-300 hover:border-accent-purple/50
                 shadow-sm hover:shadow-accent-purple/20"
    >
      {/* Thumbnail */}
      <div className="relative aspect-video bg-light-100 overflow-hidden">
        {video.thumbnail ? (
          <img
            src={video.thumbnail}
            alt={video.title}
            className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-110"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-accent-purple/10 to-accent-blue/10">
            <svg className="w-12 h-12 text-gray-400" fill="currentColor" viewBox="0 0 24 24">
              <path d="M19.615 3.184c-3.604-.246-11.631-.245-15.23 0C.488 3.45.029 5.804 0 12c.029 6.185.484 8.549 4.385 8.816 3.6.245 11.626.246 15.23 0C23.512 20.55 23.971 18.196 24 12c-.029-6.185-.484-8.549-4.385-8.816zm-10.615 12.816v-8l8 3.993-8 4.007z"/>
            </svg>
          </div>
        )}

        {/* Duration badge */}
        {video.duration && (
          <span className="absolute bottom-2 right-2 bg-black/80 text-white text-xs px-2 py-1 rounded">
            {formatDuration(video.duration)}
          </span>
        )}

        {/* Transcript indicator */}
        {video.has_transcript && (
          <div className="absolute top-2 right-2 bg-accent-purple/90 text-white text-xs px-2 py-1 rounded">
            📝
          </div>
        )}
      </div>

      {/* Info */}
      <div className="p-4">
        <h3 className="font-semibold text-sm text-gray-900 line-clamp-2 group-hover:text-accent-purple transition-colors">
          {video.title}
        </h3>
        <div className="mt-2 flex items-center justify-between text-xs text-gray-500">
          <span>{formatDate(video.upload_date)}</span>
          <span className="text-accent-blue">Watch →</span>
        </div>
      </div>
    </div>
  );
}
