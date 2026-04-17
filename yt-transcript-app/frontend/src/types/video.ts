export interface Video {
  id: string;
  title: string;
  thumbnail: string | null;
  upload_date: string | null;
  duration: number | null;
  has_transcript: boolean;
}

export interface TranscriptLine {
  start: number;
  end: number;
  text: string;
}

export interface VideoListResponse {
  videos: Video[];
  last_updated: string | null;
}

export interface TranscriptResponse {
  video_id: string;
  title: string;
  lines: TranscriptLine[];
}