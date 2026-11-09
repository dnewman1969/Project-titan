/** Camera and microphone for the webcam tile. Every other permission stays denied. */
export function allowCapturePermission(permission: string): boolean {
  return permission === "media";
}
