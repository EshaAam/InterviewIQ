"use client";

import { useEffect, useState } from "react";
import { describeError, getSkillMap, type SkillMap } from "@/lib/api";
import { CountUp } from "@/components/motion";
import { HeroTile, PageHero } from "@/components/page-hero";
import { countByStatus, SkillMapView } from "@/components/skill-map";
import { ErrorBanner, PageLoading, Shell } from "@/components/ui";

export default function SkillsPage() {
  const [map, setMap] = useState<SkillMap | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSkillMap()
      .then((loaded) => {
        if (!cancelled) setMap(loaded);
      })
      .catch((err) => {
        if (!cancelled) setError(describeError(err, "Could not load your skills"));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <Shell width="narrow">
        <ErrorBanner message={error} />
      </Shell>
    );
  }
  if (!map) return <PageLoading />;

  const counts = countByStatus(map);
  const interviews =
    map.sessions_assessed === 1 ? "1 graded interview" : `${map.sessions_assessed} graded interviews`;

  return (
    <>
      <PageHero
        back={{ href: "/interview", label: "My interviews" }}
        eyebrow="Across all your interviews"
        title="My skills"
        subtitle={`Where each skill stands after ${interviews}, with the answers behind it. A skill is placed by the most recent interview that asked about it.`}
      >
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <HeroTile value={<CountUp value={counts.demonstrated} />} label="Demonstrated" />
          <HeroTile value={<CountUp value={counts.developing} />} label="Developing" />
          <HeroTile value={<CountUp value={counts.weak} />} label="Need work" />
          <HeroTile value={<CountUp value={map.not_assessed.length} />} label="Not assessed" />
        </div>
      </PageHero>
      <Shell>
        <SkillMapView map={map} />
      </Shell>
    </>
  );
}
