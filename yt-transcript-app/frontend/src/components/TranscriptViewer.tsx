import { TranscriptLine } from '../types/video';

interface TranscriptViewerProps {
  lines: TranscriptLine[];
  viewMode: 'segmented' | 'full';
}

function formatTimestamp(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

export function TranscriptViewer({ lines, viewMode }: TranscriptViewerProps) {
  if (viewMode === 'full') {
    const fullText = lines.map(line => line.text).join(' ');
    return (
      <div className="max-h-[60vh] overflow-y-auto pr-2">
        <p className="text-gray-300 leading-relaxed whitespace-pre-wrap">{fullText}</p>
      </div>
    );
  }

  return (
    <div className="space-y-1 max-h-[60vh] overflow-y-auto pr-2">
      {lines.map((line, index) => (
        <div
          key={index}
          className="group flex gap-3 p-2 rounded-lg hover:bg-dark-700 transition-colors cursor-pointer"
        >
          <span className="text-xs text-gray-600 font-mono pt-1 min-w-[3rem]">
            {formatTimestamp(line.start)}
          </span>
          <p className="text-gray-300 leading-relaxed group-hover:text-white transition-colors">
            {line.text}
          </p>
        </div>
      ))}
    </div>
  );
}
