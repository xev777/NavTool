# NavTool 1.1.2

**Fixes the Windows Defender false alarm of 1.1.1.** / **Corrige la falsa alarma de Windows Defender de la 1.1.1.**

## What happened / Qué pasó
Microsoft Defender flagged `NavTool.exe` from 1.1.1 as `Behavior:Win32/Impact.A!ml` and quarantined it right after installing.
The cause was the Microsoft Store apps wizard: it relaunched NavTool **elevated with a hidden window**, a pattern that antivirus
engines associate with malware. / Defender marcó el `NavTool.exe` de la 1.1.1 y lo puso en cuarentena al instalar. La causa era
el asistente de apps de la Tienda: relanzaba NavTool **con permisos elevados y ventana oculta**, patrón que los antivirus asocian con malware.

## What changed / Qué cambió
- The wizard now uses a normal, visible administrator prompt. Version 1.1 and 1.1.2 are not detected; 1.1.1 was. / El asistente usa
  el aviso de administrador normal y visible.
- The build now **scans the executable with Defender and stops if it is flagged**; a test forbids hidden elevations.
  / La compilación **analiza el ejecutable con Defender y se detiene si lo marca**.
- Everything from 1.1.1 is kept (Store apps compatibility). / Se mantiene todo lo de la 1.1.1.

## If you installed 1.1.1 / Si instalaste la 1.1.1
Uninstall it (Settings → Apps → NavTool) and install 1.1.2. If Windows Security shows a "Behavior:Win32/Impact.A!ml" item in
*Protection history*, it belongs to 1.1.1. / Desinstálala (Configuración → Aplicaciones → NavTool) e instala la 1.1.2.

## Notes / Notas
- The executables are **not code-signed**; SmartScreen or another antivirus may still warn about an unknown publisher. If your
  antivirus flags NavTool, please report it (Issues) and submit the file as a false positive to your vendor. Check the SHA-256.
  / Los ejecutables **no están firmados**: si tu antivirus lo marca, avísalo y envíalo como falso positivo. Comprueba el SHA-256.
- Licensed under **GPL-3.0**. / Licencia **GPL-3.0**.
