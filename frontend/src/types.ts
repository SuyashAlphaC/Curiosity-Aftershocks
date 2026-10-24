export interface Point {
  date: string;
  day: number;
  views: number;
  lift: number;
  z: number;
}
export interface Topic {
  id: string;
  title: string;
  category: string;
  baseline: number;
  totalViews: number;
  excessViews: number;
  peakLift: number;
  peakZ: number;
  peakDay: number;
  burstDays: number;
  cluster: number;
  series: Point[];
}
export interface Edge {
  source: string;
  target: string;
  correlation: number;
  lag: number;
}
export interface Study {
  id: string;
  title: string;
  shortTitle: string;
  date: string;
  category: string;
  location: string;
  description: string;
  seed: string;
  stats: {
    totalViews: number;
    excessViews: number;
    peakLift: number;
    topics: number;
  };
  evaluation: { mae: number; wape: number };
  topics: Topic[];
  edges: Edge[];
  timeline: { day: number; date: string; views: number; baseline: number }[];
}
export interface Pipeline {
  engine: string;
  master: string;
  records: number;
  invalidRecords: number;
  durationSeconds: number;
  recordsPerSecond: number;
  builtAt: string;
  partitions: number;
  clustering: string;
  granularity: string;
  dataMode: string;
  limitations: string[];
  source: {
    source: string;
    license: string;
    retrieved_at: string;
    sha256: string;
    requests: {
      article: string;
      event_id: string;
      url: string;
      records: number;
    }[];
  };
  bulk?: {
    records: number;
    validRecords: number;
    rejectedRecords: number;
    durationSeconds: number;
    recordsPerSecond: number;
    inputBytes: number;
    files: string[];
    topArticles: { article: string; views: number }[];
    note: string;
  };
}
