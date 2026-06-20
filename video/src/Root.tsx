import { Composition } from "remotion";
import { Demo, FPS, DURATION } from "./Video";
import { License, LIC_FPS, LIC_DURATION } from "./License";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="Demo"
        component={Demo}
        durationInFrames={DURATION}
        fps={FPS}
        width={1920}
        height={1080}
      />
      <Composition
        id="License"
        component={License}
        durationInFrames={LIC_DURATION}
        fps={LIC_FPS}
        width={1920}
        height={1080}
      />
    </>
  );
};
