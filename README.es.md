# NTnRoute.AI

[English](README.md) | [Indonesia](README.id.md) | [Español](README.es.md) | [日本語](README.ja.md) | [Deutsch](README.de.md)

Motor de gestión de dispositivos de red por SSH para agentes de IA: un pequeño inventario de dispositivos, ejecución segura de CLI, copia de seguridad de configuraciones y cambios de configuración **con puerta de aprobación** y rollback automático — junto con un conjunto de skills de [Hermes Agent](https://hermes-agent.nousresearch.com) que enseñan al agente a usarlo de forma responsable.

## Qué hace

- **Inventario** — registra un dispositivo una vez (`ntn add`); el motor prueba la conexión SSH, obtiene el hostname y la configuración en ejecución, y solo entonces lo guarda. Todo se almacena en un archivo JSON plano (`~/.ntnroute/devices.json`, modo 600) que sobrevive a los reinicios del agente.
- **Acceso de solo lectura** — el motor ejecuta comandos tipo `show ...` a petición y devuelve la transcripción.
- **Copia de seguridad** — `ntn sync` guarda la configuración en ejecución en el inventario y almacena una instantánea con marca de tiempo; cada cambio exitoso (y cada rollback) publica un par de archivos en `~/.ntnroute/backups/<host>/<YYYY-MM>/`. Cada carpeta mensual contiene hasta 4 pares de cambios y 4 instantáneas de sync/add, conservados los últimos 3 meses más uno anual; los archivos sueltos de versiones anteriores se reubican automáticamente en este diseño.
- **Cambios de configuración con puerta** — `ntn config` ejecuta: snapshot previo → aplicar → guardar → actualización del inventario/archivo. Solo falla ante un error de comando del dispositivo, sesión perdida o snapshot previo no disponible. El éxito funcional se confirma después con comprobaciones de solo lectura planificadas en el dispositivo.
- **Rollback** — cada cambio guarda un checkpoint; el script de deshacer almacenado puede reproducirse a petición.
- **Registro de auditoría** — cada intento de config/rollback se registra *antes* de tocar el dispositivo (`config-pending`) y luego se cierra: `config-ok`/`config-failed`/`config-aborted` más un marcador `config-started` para el historial. Los filtros del registro de cambios sirven para troubleshooting y revisión de seguridad: `pending` (intentos sin veredicto alguno — proceso muerto a mitad del apply), `failed`, `config`, `all`. Las entradas con más de 105 días se podan automáticamente.

El motor es solo bash + jq + OpenSSH — sin Python, sin agentes, sin demonios.
Los scripts auxiliares (`rollback_gen`, `ios_session.sh`) también son bash + awk.
La auditoría y el troubleshooting son procedimientos guiados del agente: sin
scripts de auditoría o triaje incluidos.

## Plataformas soportadas

| Fabricante | Modo | Obtener config | Guardar |
|---|---|---|---|
| Cisco IOS | PTY interactivo | `show running-config` | `write memory` |
| Huawei VRP | PTY interactivo | `display current-configuration` | `save` + confirmación |
| Aruba / Arista / Ruijie | PTY interactivo | `show running-config` | `write memory` |
| Juniper Junos | PTY interactivo | `show configuration \| display set` | `commit` (dentro del modo config) |
| Fortinet FortiGate | PTY interactivo | `show full-configuration` | automático (se aplica al enviar) |
| MikroTik RouterOS | modo exec (`ssh -T`) | `/export verbose` | automático |
| Linux (SSH) | modo exec (`ssh -T`) | snapshot `uname -a` + os-release | — (sin modelo de configuración) |
| Windows (OpenSSH, cmd.exe) | exec-arg (`ssh host "cmd"`) | snapshot `systeminfo` | — (sin modelo de configuración) |

La criptografía legacy (imágenes Cisco antiguas) está soportada: `diffie-hellman-group14-sha1`, `ssh-rsa`, `aes128-cbc`, `hmac-sha1` se negocian cuando hace falta.

## Adaptarse a nuevos fabricantes

El comportamiento por marca vive en `~/.ntnroute/brands.json` — edítalo para soportar un fabricante que el motor no conoce, o para sobrescribir uno integrado (cambios de firmware incluidos). Una entrada basta:

```json
{
  "zte": {
    "paging": "terminal length 0",
    "config_enter": "configure terminal",
    "config_leave": "end",
    "save_lines": ["write memory"],
    "config_show": "show running-config",
    "hostname_show": "show running-config | include hostname",
    "hostname_field": "hostname",
    "err_pattern": "(^%|Invalid input)"
  }
}
```

Campos: `paging`, `secret_cmd`, `config_enter`, `config_leave`, `save_lines` (array), `save_delay`, `config_show`, `hostname_show`, `hostname_field` (`hostname`|`sysname`|`host-name`|`colon`), `err_pattern` (grep -E), `negate_prefix` (usado por `rollback_gen`). Las marcas desconocidas sin perfil usan valores genéricos tipo Cisco y se saltan el paso de guardado. El instalador nunca sobrescribe tu `brands.json`.

## Formato de la base de datos de dispositivos

El inventario vive en `~/.ntnroute/devices.json` (modo 600, gitignored — nunca confirmes el archivo real). El motor lee y escribe una forma exacta: `next_id`, `devices[]`, `checkpoints[]`, `audit[]`. Consulta [`examples/devices.example.json`](examples/devices.example.json) como referencia rellenada con credenciales de ejemplo — apunta a cualquier agente de IA o script a ese archivo para que use los mismos nombres de campo en vez de inventar los suyos.

## Instalación

Requisitos: Linux, macOS o Windows (vía Git for Windows) con `bash`, `jq`, `ssh` (OpenSSH). macOS necesita GNU coreutils para `timeout` (`brew install coreutils`).

```bash
git clone https://github.com/Dandi41/ntnroute.git
cd ntnroute
./install.sh
```

El instalador:

1. comprueba `jq` y `ssh`,
2. instala el motor en `~/.ntnroute/ntn` (modo 700) y crea el enlace simbólico `~/.local/bin/ntn`,
3. crea `~/.ntnroute/` con un inventario vacío (modo 600),
4. si usas [Hermes Agent](https://hermes-agent.nousresearch.com), copia las cinco skills a `~/.hermes/skills/networking/`.

### Windows (nativo, sin WSL)

NTnRoute también se ejecuta de forma nativa en Windows mediante Git for Windows (bash MSYS2) — sin necesidad de WSL.

1. Instala [Git for Windows](https://git-scm.com/download/win) — incluye `bash` y `ssh` de OpenSSH.
2. Abre **Git Bash** y ejecuta:

```bash
git clone -b beta https://github.com/Dandi41/ntnroute.git ~/ntnroute
cd ~/ntnroute
bash install.sh
```

En Windows el instalador detecta MSYS2 automáticamente: el motor se instala en `~/.ntnroute/ntn`, `ntn` se coloca en `~/.local/bin` como copia (los symlinks de Windows requieren privilegios) y, si falta `jq`, descarga `jq.exe` en `~/.ntnroute/bin` (el motor añade ese directorio al `PATH` por sí mismo en tiempo de ejecución). Si el shell no encuentra `ntn` tras la instalación, añade `~/.local/bin` al PATH como sugiere el instalador. Todos los comandos se comportan igual que en Linux/macOS; las sesiones interactivas de fabricantes usan la PTY de MSYS2. El soporte de Windows está en la rama `beta` hasta que se fusione.

## Inicio rápido

Si no sabes cómo usar el motor NTnRoute, escribe `ntn` o `ntn help` a tu agente. El agente mostrará el menú disponible y guiará el flujo de trabajo adecuado.

```bash
# registra un dispositivo (primero prueba la conexión; si falla, no se guarda)
ntn add 10.0.0.5 22 admin S3cr3t! Router Cisco enablepass123

# menú de inventario y resumen de configuración
ntn list
ntn add <IP> <Port> <User> <Pass> <Type> <Brand> [Secret]
ntn remove <number|id>
ntn show <ref>
ntn sync <ref|all>
```

Un cambio de configuración es siempre: plan → aprobación → aplicar → verificar. La skill `network-change-management` impone la puerta de aprobación y genera el script de rollback antes de tocar el dispositivo.

## Las skills incluidas

| Skill | Propósito |
|---|---|
| `ntnroute` | Reglas de flujo de trabajo del motor `ntn` (inventario, exec, config, rollback) |
| `network-device-cli` | Mecánica de sesiones SSH por fabricante, cripto legacy, análisis de credenciales |
| `network-change-management` | Puerta de plan/aprobación, generación de rollback |
| `network-troubleshooting` | Diagnóstico OSI-first con referencias de comandos por fabricante |
| `network-security-audit` | Auditoría de hardening local + perímetro de las configuraciones |

## Notas de seguridad

- Las contraseñas se guardan **en texto plano** en `~/.ntnroute/devices.json` (modo 600, solo el propietario). Cuida bien ese archivo para que no se difunda fuera de la máquina.
- `ntn show <ref>` enmascara las contraseñas por defecto.
- Los backups de configuración en `~/.ntnroute/backups/` contienen los mismos secretos de los dispositivos — trátalos con el mismo cuidado.
## Estado y honestidad

Probado de extremo a extremo en dispositivos reales: Cisco IOS 15.4 y MikroTik RouterOS 7.18.2 (add/list/show/exec/sync, config + post-verificación, rollback, comandos destructivos, guardia de dispositivo inaccesible, guardia de error del dispositivo). Las demás marcas (Huawei VRP, Arista EOS, Aruba AOS-CX, Ruijie RGOS, Juniper Junos, Fortinet FortiGate) se verificaron igual contra CLIs de fabricante emulados (arnés de pruebas local, no forma parte del toolkit).

Las rutas de código para Huawei, Aruba, Arista, Ruijie y Juniper existen pero **no** se han probado aún contra hardware real — trátalas como experimentales y reporta problemas en Issues.

## Apoyar

Si ntnroute te ahorra tiempo, puedes invitar al creador a un lemper 🙂 — un bocadillo indonesio de arroz glutinoso: **[tako.id/Lemper41](https://tako.id/Lemper41)**

Encuéntrame en [Instagram](https://www.instagram.com/sdandi_41/) y [LinkedIn](https://www.linkedin.com/in/dandi-suryadi-a29276253/).

## Licencia

[MIT](LICENSE) © Dandi Suryadi
