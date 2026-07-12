import * as THREE from "three";

export class FlyControls {
  readonly velocity = new THREE.Vector3();
  private readonly keys = new Set<string>();
  private yaw = 0;
  private pitch = -0.32;
  private readonly targetVelocity = new THREE.Vector3();
  private readonly forward = new THREE.Vector3();
  private readonly right = new THREE.Vector3();
  private readonly up = new THREE.Vector3(0, 1, 0);

  constructor(
    private readonly camera: THREE.PerspectiveCamera,
    domElement: HTMLElement,
  ) {
    this.camera.position.set(0, 21, 18);
    this.applyRotation();
    domElement.addEventListener("click", () => domElement.requestPointerLock());
    document.addEventListener("pointerlockchange", () => {
      domElement.classList.toggle("locked", document.pointerLockElement === domElement);
    });
    document.addEventListener("mousemove", (event) => {
      if (document.pointerLockElement !== domElement) {
        return;
      }
      this.yaw -= event.movementX * 0.0021;
      this.pitch -= event.movementY * 0.0021;
      this.pitch = Math.max(-1.35, Math.min(0.42, this.pitch));
      this.applyRotation();
    });
    window.addEventListener("keydown", (event) => this.keys.add(event.code));
    window.addEventListener("keyup", (event) => this.keys.delete(event.code));
  }

  update(dt: number): void {
    this.forward.set(0, 0, -1).applyQuaternion(this.camera.quaternion);
    this.forward.y = 0;
    this.forward.normalize();
    this.right.crossVectors(this.forward, this.up).normalize();

    const input = new THREE.Vector3();
    if (this.keys.has("KeyW")) input.add(this.forward);
    if (this.keys.has("KeyS")) input.sub(this.forward);
    if (this.keys.has("KeyD")) input.add(this.right);
    if (this.keys.has("KeyA")) input.sub(this.right);
    if (this.keys.has("Space") || this.keys.has("KeyE")) input.y += 1;
    if (this.keys.has("ControlLeft") || this.keys.has("KeyQ")) input.y -= 1;
    if (input.lengthSq() > 0) {
      input.normalize();
    }

    const speed = this.keys.has("ShiftLeft") || this.keys.has("ShiftRight") ? 64 : 34;
    this.targetVelocity.copy(input.multiplyScalar(speed));
    const smoothing = 1 - Math.exp(-dt * 8.5);
    this.velocity.lerp(this.targetVelocity, smoothing);
    this.camera.position.addScaledVector(this.velocity, dt);
    this.camera.position.y = Math.max(5, Math.min(96, this.camera.position.y));
  }

  private applyRotation(): void {
    this.camera.rotation.order = "YXZ";
    this.camera.rotation.y = this.yaw;
    this.camera.rotation.x = this.pitch;
  }
}
