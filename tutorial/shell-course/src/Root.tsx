import React from "react";
import { Composition } from "remotion";
import { FPS, H, W } from "./theme";
import { totalFrames, Video } from "./Video";

export const Root: React.FC = () => (
  <Composition id="ShellCourse" component={Video} durationInFrames={totalFrames} fps={FPS} width={W} height={H} />
);
