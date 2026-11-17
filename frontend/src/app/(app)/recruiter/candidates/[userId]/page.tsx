"use client";

import { use, useEffect, useState } from "react";
import { describeError, getCandidateSkillMap, type SkillMap } from "@/lib/api";
import { CountUp } from "@/components/motion";
import { HeroTile, PageHero } from "@/components/page-hero";
import { countByStatus, SkillMapView } from "@/components/skill-map";
import { BackLink, ErrorBanner, PageLoading, Shell } from "@/components/ui";

export default function CandidateSkillMapPage({
  params,
}: {
  params: Promise<{ userId: string }>;
}) {
  const { userId } = use(params);
  const [map, setMap] = useState<SkillMap | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getCandidateSkillMap(userId)
      .then((loaded) => {
        if (!cancelled) setMap(loaded);
      })
      .catch((err) => {
        if (!cancelled) setError(describeError(err, "Could not load this candidate's skills"));
      });
    return () => {
      cancelled = true;
    };
  }, [userId]);

  if (error) {
    return (
      <Shell width="narrow">
        <div className="flex flex-col gap-4">
          <BackLink href="/recruiter/sessions">All sessions</BackLink>
          <ErrorBanner message={error} />
        </div>
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
        back={{ href: "/recruiter/sessions", label: "All sessions" }}
        eyebrow="Candidate skill map"
        title={map.candidate_email ?? "Candidate"}
        subtitle={`Across ${interviews}. A skill is placed by the most recent interview that asked about it; open one to see the answers behind it.`}
      >
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <HeroTile value={<CountUp value={counts.demonstrated} />} label="Demonstrated" />
          <HeroTile value={<CountUp value={counts.developing} />} label="Developing" />
          <HeroTile value={<CountUp value={counts.weak} />} label="Need work" />
          <HeroTile value={<CountUp value={map.not_assessed.length} />} label="Not assessed" />
        </div>
      </PageHero>
      <Shell>
        <SkillMapView map={map} forRecruiter />
      </Shell>
    </>
  );
}
