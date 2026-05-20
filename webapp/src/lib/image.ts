export function imageSrc(value?: string | null) {
  if (!value) return "";
  return value.startsWith("data:") ? value : `data:image/jpeg;base64,${value}`;
}
