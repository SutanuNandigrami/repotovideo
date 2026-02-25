export interface RepoData {
  name: string;
  fullName: string;
  description: string;
  stars: number;
  forks: number;
  language: string;
  hookStyle: "counter" | "momentum" | "problem";
  hookText: string;
  tagline: string;
  features: Array<{ emoji: string; title: string; desc: string }>;
  techStack: Array<{ emoji: string; name: string }>;
  style?:
    | "repo-promo"
    | "explainer"
    | "story"
    | "listicle"
    | "myth-vs-fact"
    | "case-study"
    | "launch-teaser";
  requestedStyle?:
    | "auto"
    | "repo-promo"
    | "explainer"
    | "story"
    | "listicle"
    | "myth-vs-fact"
    | "case-study"
    | "launch-teaser";
  styleReason?: string;
}
