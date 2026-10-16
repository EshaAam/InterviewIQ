/** The InterviewIQ mark and wordmark. The mark tilts and brightens on hover. */
export function Logo({ size = "md", tone = "dark" }: { size?: "md" | "lg"; tone?: "dark" | "light" }) {
  const mark = size === "lg" ? "size-10 rounded-xl text-base" : "size-8.5 rounded-[10px] text-sm";
  const word = size === "lg" ? "text-[22px]" : "text-[19px]";
  return (
    <span className="group/logo flex items-center gap-2.5">
      <span
        className={`flex items-center justify-center font-display font-bold text-ink-inv transition-[background,transform] duration-250 ease-out-soft group-hover/logo:-rotate-6 group-hover/logo:bg-accent ${mark} ${
          tone === "dark" ? "bg-brand" : "bg-white/12 ring-1 ring-white/20"
        }`}
      >
        IQ
      </span>
      <span
        className={`font-display font-bold ${word} ${tone === "dark" ? "text-ink" : "text-ink-inv"}`}
      >
        InterviewIQ
      </span>
    </span>
  );
}
