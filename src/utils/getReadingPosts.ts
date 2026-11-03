import type { CollectionEntry } from "astro:content";
import { getSortedPosts } from "./getSortedPosts";

export function getReadingPosts(posts: CollectionEntry<"posts">[]) {
  return getSortedPosts(posts).sort(
    (a, b) => (a.data.seriesOrder ?? Number.MAX_SAFE_INTEGER) - (b.data.seriesOrder ?? Number.MAX_SAFE_INTEGER)
  );
}
