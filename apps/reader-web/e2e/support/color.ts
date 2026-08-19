export type RgbaColor = readonly [red: number, green: number, blue: number, alpha: number];

const numberPattern = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i;

function parseNumber(value: string, maximum: number, percentageScale: number): number {
  const trimmed = value.trim();
  const percentage = trimmed.endsWith("%");
  const numberText = percentage ? trimmed.slice(0, -1).trim() : trimmed;
  if (!numberPattern.test(numberText)) throw new Error(`Invalid CSS color channel: ${value}`);
  const parsed = Number(numberText) * (percentage ? percentageScale : 1);
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > maximum) {
    throw new Error(`CSS color channel is out of range: ${value}`);
  }
  return parsed;
}

function parseHexColor(color: string): RgbaColor | null {
  const matched = color.match(/^#([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$/i)?.[1];
  if (matched == null) return null;
  const expanded = matched.length <= 4 ? [...matched].map((character) => character.repeat(2)).join("") : matched;
  return [
    Number.parseInt(expanded.slice(0, 2), 16),
    Number.parseInt(expanded.slice(2, 4), 16),
    Number.parseInt(expanded.slice(4, 6), 16),
    expanded.length === 8 ? Number.parseInt(expanded.slice(6, 8), 16) / 255 : 1,
  ];
}

export function parseCssRgb(color: string): RgbaColor {
  const trimmed = color.trim();
  const hex = parseHexColor(trimmed);
  if (hex != null) return hex;

  const functional = trimmed.match(/^rgba?\((.*)\)$/i);
  if (functional == null) throw new Error(`Expected CSS rgb color, received ${color}`);
  const body = functional[1].trim();
  let channelValues: string[];
  let alphaValue: string | undefined;

  if (body.includes(",")) {
    if (body.includes("/")) throw new Error(`Invalid comma-separated CSS rgb color: ${color}`);
    const parts = body.split(",").map((part) => part.trim());
    if (parts.length !== 3 && parts.length !== 4) throw new Error(`Invalid CSS rgb color: ${color}`);
    channelValues = parts.slice(0, 3);
    alphaValue = parts[3];
  } else {
    const slashParts = body.split("/").map((part) => part.trim());
    if (slashParts.length > 2) throw new Error(`Invalid CSS rgb color: ${color}`);
    channelValues = slashParts[0].split(/\s+/).filter(Boolean);
    if (channelValues.length !== 3) throw new Error(`Invalid CSS rgb color: ${color}`);
    alphaValue = slashParts[1];
  }

  return [
    parseNumber(channelValues[0], 255, 2.55),
    parseNumber(channelValues[1], 255, 2.55),
    parseNumber(channelValues[2], 255, 2.55),
    alphaValue === undefined ? 1 : parseNumber(alphaValue, 1, 0.01),
  ];
}

export function compositeColors(foreground: RgbaColor, background: RgbaColor): RgbaColor {
  const alpha = foreground[3] + background[3] * (1 - foreground[3]);
  if (alpha === 0) return [0, 0, 0, 0];
  return [
    (foreground[0] * foreground[3] + background[0] * background[3] * (1 - foreground[3])) / alpha,
    (foreground[1] * foreground[3] + background[1] * background[3] * (1 - foreground[3])) / alpha,
    (foreground[2] * foreground[3] + background[2] * background[3] * (1 - foreground[3])) / alpha,
    alpha,
  ];
}

export function compositeCssLayers(colors: readonly string[]): RgbaColor {
  return colors
    .map(parseCssRgb)
    .reduceRight<RgbaColor>((background, foreground) => compositeColors(foreground, background), [0, 0, 0, 0]);
}

export function contrastRatio(foreground: string, background: string): number {
  const backgroundColor = parseCssRgb(background);
  if (backgroundColor[3] !== 1) throw new Error(`Contrast background must be opaque, received ${background}`);
  const foregroundColor = compositeColors(parseCssRgb(foreground), backgroundColor);
  const luminance = ([red, green, blue]: RgbaColor) => {
    const [linearRed, linearGreen, linearBlue] = [red, green, blue].map((channel) => {
      const normalized = channel / 255;
      return normalized <= 0.04045 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * linearRed + 0.7152 * linearGreen + 0.0722 * linearBlue;
  };
  const [light, dark] = [luminance(foregroundColor), luminance(backgroundColor)].sort((a, b) => b - a);
  return (light + 0.05) / (dark + 0.05);
}
