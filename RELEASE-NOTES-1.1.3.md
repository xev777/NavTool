# NavTool 1.1.3

**Optional PayPal donation link, and code-signing preparation.** / **Enlace de donación opcional por PayPal, y preparación de la firma de código.**

## New / Novedades
- **Optional support link**: the About screen can show a "copy PayPal email" button. It stays hidden unless configured
  and is never a pop-up. / **Enlace de apoyo opcional**: el «Acerca de» puede mostrar un botón para copiar el correo de
  PayPal. Permanece oculto salvo que esté configurado, y nunca aparece como ventana emergente.

## Under the hood / Por dentro
- Builds now run on GitHub Actions instead of a personal computer, and the executable/installer carry version metadata
  (product, version, author, license) — both required for the free code-signing application submitted to the
  [SignPath Foundation](https://signpath.org/). See [CODE_SIGNING_POLICY.md](CODE_SIGNING_POLICY.md) and
  [PRIVACY.md](PRIVACY.md). / Las compilaciones se hacen ahora en GitHub Actions, y el ejecutable/instalador llevan
  metadatos de versión — ambos requisitos de la solicitud de firma gratuita a SignPath Foundation.
- `compilar.ps1` only closes a NavTool process launched from its own build folder, never one you have installed or
  running. / `compilar.ps1` solo cierra un NavTool lanzado desde su propia carpeta de compilación.

## Notes / Notas
- The executables are still **not code-signed** while the SignPath Foundation application is pending; SmartScreen may
  warn. Check the SHA-256 below. / Los ejecutables **aún no están firmados** mientras la solicitud a SignPath está
  pendiente; SmartScreen puede avisar. Comprueba el SHA-256.
- Licensed under **GPL-3.0**. / Licencia **GPL-3.0**.

Full history: [CHANGELOG.md](CHANGELOG.md). / Historial completo: [CHANGELOG.md](CHANGELOG.md).
