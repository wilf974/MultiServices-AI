import React from "react";
import {
  AbsoluteFill,
  Sequence,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
  Easing,
} from "remotion";

export const FPS = 30;
export const DURATION = 1200; // 40s

const C = {
  bg: "#0a0e16",
  panel: "#111a2b",
  panelEdge: "#1e2c44",
  ink: "#e8eefb",
  muted: "#8a99b6",
  mint: "#3df5c4",
  blue: "#7aa2ff",
  warn: "#ff5d6c",
  gold: "#ffcf5c",
};

const MONO = "'SF Mono','DejaVu Sans Mono','Courier New',monospace";
const SANS = "'Segoe UI','Helvetica Neue',system-ui,sans-serif";

// ---------- helpers ----------
const useReveal = (delay: number, dur = 18) => {
  const frame = useCurrentFrame();
  const t = interpolate(frame, [delay, delay + dur], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
  return { opacity: t, y: (1 - t) * 22 };
};

const Glow: React.FC = () => {
  const frame = useCurrentFrame();
  const drift = Math.sin(frame / 80) * 30;
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ background: C.bg }} />
      <div
        style={{
          position: "absolute",
          width: 1100,
          height: 1100,
          left: -200 + drift,
          top: -350,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(61,245,196,0.16), transparent 60%)",
          filter: "blur(20px)",
        }}
      />
      <div
        style={{
          position: "absolute",
          width: 1200,
          height: 1200,
          right: -300 - drift,
          bottom: -450,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(122,162,255,0.14), transparent 60%)",
          filter: "blur(20px)",
        }}
      />
      {/* grid */}
      <AbsoluteFill
        style={{
          backgroundImage:
            "linear-gradient(rgba(255,255,255,0.035) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.035) 1px, transparent 1px)",
          backgroundSize: "64px 64px",
          maskImage: "radial-gradient(circle at 50% 45%, black, transparent 80%)",
          WebkitMaskImage: "radial-gradient(circle at 50% 45%, black, transparent 80%)",
        }}
      />
      {/* vignette */}
      <AbsoluteFill
        style={{
          boxShadow: "inset 0 0 320px rgba(0,0,0,0.75)",
        }}
      />
    </AbsoluteFill>
  );
};

const Kicker: React.FC<{ text: string; color?: string; delay?: number }> = ({
  text,
  color = C.mint,
  delay = 0,
}) => {
  const r = useReveal(delay);
  return (
    <div
      style={{
        fontFamily: MONO,
        fontSize: 26,
        letterSpacing: 8,
        textTransform: "uppercase",
        color,
        opacity: r.opacity,
        transform: `translateY(${r.y}px)`,
      }}
    >
      {text}
    </div>
  );
};

// ---------- Scene 1: Title ----------
const Title: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 200 }, durationInFrames: 30 });
  const sub = useReveal(34);
  const cap = useReveal(58);
  const fadeOut = interpolate(frame, [88, 105], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        textAlign: "center",
        opacity: fadeOut,
      }}
    >
      <div style={{ transform: `scale(${0.9 + pop * 0.1})`, opacity: pop }}>
        <Kicker text="MultiService IA" />
      </div>
      <div
        style={{
          fontFamily: SANS,
          fontWeight: 800,
          fontSize: 96,
          lineHeight: 1.05,
          marginTop: 26,
          color: C.ink,
          opacity: sub.opacity,
          transform: `translateY(${sub.y}px)`,
        }}
      >
        LLMs forget.
        <br />
        <span style={{ color: C.mint }}>Your memory shouldn&apos;t.</span>
      </div>
      <div
        style={{
          fontFamily: MONO,
          fontSize: 27,
          marginTop: 34,
          color: C.muted,
          opacity: cap.opacity,
          transform: `translateY(${cap.y}px)`,
        }}
      >
        A 40-second story about a truth that changed.
      </div>
    </AbsoluteFill>
  );
};

// ---------- Scene 2: Timeline ----------
const Row: React.FC<{
  delay: number;
  day: string;
  tag: string;
  tagColor: string;
  text: React.ReactNode;
  note?: string;
}> = ({ delay, day, tag, tagColor, text, note }) => {
  const r = useReveal(delay);
  return (
    <div
      style={{
        display: "flex",
        gap: 28,
        alignItems: "flex-start",
        opacity: r.opacity,
        transform: `translateY(${r.y}px)`,
      }}
    >
      <div
        style={{
          fontFamily: MONO,
          fontSize: 30,
          color: C.muted,
          width: 150,
          textAlign: "right",
          paddingTop: 16,
        }}
      >
        {day}
      </div>
      <div
        style={{
          width: 18,
          height: 18,
          borderRadius: "50%",
          background: tagColor,
          marginTop: 22,
          boxShadow: `0 0 18px ${tagColor}`,
          flexShrink: 0,
        }}
      />
      <div
        style={{
          background: C.panel,
          border: `1px solid ${C.panelEdge}`,
          borderLeft: `4px solid ${tagColor}`,
          borderRadius: 14,
          padding: "20px 28px",
          minWidth: 760,
        }}
      >
        <div
          style={{
            fontFamily: MONO,
            fontSize: 20,
            letterSpacing: 3,
            color: tagColor,
            textTransform: "uppercase",
            marginBottom: 8,
          }}
        >
          {tag}
        </div>
        <div style={{ fontFamily: SANS, fontSize: 40, fontWeight: 700, color: C.ink }}>
          {text}
        </div>
        {note ? (
          <div style={{ fontFamily: MONO, fontSize: 21, color: C.muted, marginTop: 10 }}>
            {note}
          </div>
        ) : null}
      </div>
    </div>
  );
};

const Timeline: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useReveal(4);
  const fadeOut = interpolate(frame, [320, 345], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill
      style={{ justifyContent: "center", paddingLeft: 220, opacity: fadeOut }}
    >
      <div
        style={{
          fontFamily: SANS,
          fontSize: 34,
          color: C.ink,
          marginBottom: 46,
          opacity: head.opacity,
          transform: `translateY(${head.y}px)`,
        }}
      >
        Building <span style={{ color: C.gold, fontWeight: 700 }}>DunkBot</span> — a
        pancake-flipping robot.
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 26 }}>
        <Row
          delay={40}
          day="Day 1"
          tag="Decision"
          tagColor={C.gold}
          text="Use a NEMA-17 stepper motor."
        />
        <Row
          delay={120}
          day="Day 3"
          tag="Correction"
          tagColor={C.warn}
          text="It stalls under load — switch to an MG996R servo."
          note="supersedes the Day 1 decision (C3: closed, never deleted)"
        />
        <Row
          delay={210}
          day="Day 30"
          tag="Question"
          tagColor={C.blue}
          text="Which motor should DunkBot use?"
        />
      </div>
    </AbsoluteFill>
  );
};

// ---------- Scene 3: Split ----------
const Strike: React.FC<{ delay: number; children: React.ReactNode }> = ({
  delay,
  children,
}) => {
  const frame = useCurrentFrame();
  const w = interpolate(frame, [delay, delay + 16], [0, 100], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <span style={{ position: "relative", color: C.muted }}>
      {children}
      <span
        style={{
          position: "absolute",
          left: 0,
          top: "52%",
          height: 3,
          width: `${w}%`,
          background: C.warn,
          boxShadow: `0 0 10px ${C.warn}`,
        }}
      />
    </span>
  );
};

const Bullet: React.FC<{ delay: number; children: React.ReactNode }> = ({
  delay,
  children,
}) => {
  const r = useReveal(delay);
  return (
    <div
      style={{
        display: "flex",
        gap: 14,
        alignItems: "center",
        fontFamily: SANS,
        fontSize: 30,
        color: C.ink,
        opacity: r.opacity,
        transform: `translateX(${r.y}px)`,
      }}
    >
      <span style={{ color: C.mint, fontFamily: MONO, fontSize: 28 }}>→</span>
      {children}
    </div>
  );
};

const Split: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useReveal(4);
  const left = useReveal(28);
  const right = useReveal(54);
  const fadeOut = interpolate(frame, [455, 480], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        opacity: fadeOut,
      }}
    >
      <div
        style={{
          fontFamily: SANS,
          fontSize: 38,
          fontWeight: 700,
          color: C.ink,
          marginBottom: 44,
          opacity: head.opacity,
          transform: `translateY(${head.y}px)`,
        }}
      >
        Day 30 — same question, two memories.
      </div>
      <div style={{ display: "flex", gap: 40 }}>
        {/* WITHOUT */}
        <div
          style={{
            width: 620,
            minHeight: 360,
            background: C.panel,
            border: `1px solid ${C.warn}55`,
            borderTop: `3px solid ${C.warn}`,
            borderRadius: 18,
            padding: 38,
            opacity: left.opacity,
            transform: `translateY(${left.y}px)`,
          }}
        >
          <div
            style={{
              fontFamily: MONO,
              fontSize: 22,
              letterSpacing: 3,
              color: C.warn,
              textTransform: "uppercase",
            }}
          >
            ✕ Without memory
          </div>
          <div
            style={{
              fontFamily: SANS,
              fontSize: 44,
              fontWeight: 800,
              color: C.ink,
              marginTop: 40,
            }}
          >
            “Use a NEMA-17.”
          </div>
          <div
            style={{
              fontFamily: MONO,
              fontSize: 23,
              color: C.muted,
              marginTop: 26,
              lineHeight: 1.5,
            }}
          >
            It only recalls the first plan.
            <br />
            The correction was forgotten.
          </div>
        </div>

        {/* WITH */}
        <div
          style={{
            width: 700,
            minHeight: 360,
            background: C.panel,
            border: `1px solid ${C.mint}55`,
            borderTop: `3px solid ${C.mint}`,
            borderRadius: 18,
            padding: 38,
            opacity: right.opacity,
            transform: `translateY(${right.y}px)`,
            boxShadow: `0 0 60px rgba(61,245,196,0.10)`,
          }}
        >
          <div
            style={{
              fontFamily: MONO,
              fontSize: 22,
              letterSpacing: 3,
              color: C.mint,
              textTransform: "uppercase",
            }}
          >
            ✓ With MultiService IA
          </div>
          <div
            style={{
              fontFamily: SANS,
              fontSize: 40,
              fontWeight: 800,
              marginTop: 36,
              display: "flex",
              alignItems: "center",
              gap: 16,
              flexWrap: "wrap",
            }}
          >
            <Strike delay={70}>NEMA-17</Strike>
            <span
              style={{
                fontFamily: MONO,
                fontSize: 18,
                color: C.warn,
                border: `1px solid ${C.warn}`,
                borderRadius: 8,
                padding: "3px 10px",
              }}
            >
              STALE · C3
            </span>
          </div>
          <div
            style={{
              fontFamily: SANS,
              fontSize: 52,
              fontWeight: 800,
              color: C.mint,
              marginTop: 6,
              marginBottom: 26,
            }}
          >
            → MG996R
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <Bullet delay={120}>explains why (stalls under load)</Bullet>
            <Bullet delay={150}>shows the correction (Day 3)</Bullet>
            <Bullet delay={180}>cites its provenance</Bullet>
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ---------- Scene 4: Closing ----------
const Closing: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 200 }, durationInFrames: 34 });
  const url = useReveal(40);
  const chips = useReveal(64);
  const fadeIn = interpolate(frame, [0, 16], [0, 1], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        textAlign: "center",
        opacity: fadeIn,
      }}
    >
      <div
        style={{
          fontFamily: SANS,
          fontSize: 66,
          fontWeight: 800,
          lineHeight: 1.15,
          maxWidth: 1300,
          color: C.ink,
          transform: `scale(${0.94 + pop * 0.06})`,
        }}
      >
        Knowledge that explains{" "}
        <span style={{ color: C.mint }}>why a truth changed.</span>
      </div>
      <div
        style={{
          fontFamily: MONO,
          fontSize: 34,
          color: C.blue,
          marginTop: 42,
          opacity: url.opacity,
          transform: `translateY(${url.y}px)`,
        }}
      >
        github.com/wilf974/MultiServices-AI
      </div>
      <div
        style={{
          fontFamily: MONO,
          fontSize: 24,
          color: C.muted,
          marginTop: 26,
          letterSpacing: 2,
          opacity: chips.opacity,
          transform: `translateY(${chips.y}px)`,
        }}
      >
        Apache-2.0 &nbsp;·&nbsp; 100% local &nbsp;·&nbsp; MCP-native &nbsp;·&nbsp; bi-temporal
      </div>
    </AbsoluteFill>
  );
};

// ---------- Root composition ----------
export const Demo: React.FC = () => {
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <Glow />
      <Sequence durationInFrames={105}>
        <Title />
      </Sequence>
      <Sequence from={105} durationInFrames={345}>
        <Timeline />
      </Sequence>
      <Sequence from={450} durationInFrames={480}>
        <Split />
      </Sequence>
      <Sequence from={930} durationInFrames={270}>
        <Closing />
      </Sequence>
    </AbsoluteFill>
  );
};
