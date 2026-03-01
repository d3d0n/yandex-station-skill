// placeholder CLI for local dev; OpenClaw skill wiring will come next

const [cmd, ...args] = process.argv.slice(2);

if (!cmd || cmd === '--help' || cmd === '-h') {
  console.log(`yandex-station-skill (dev)

commands:
  list
  status <device>
  play <device> <query>
  pause <device>
  resume <device>
  next <device>
  prev <device>
  volume <device> <0-100>
`);
  process.exit(0);
}

console.log(JSON.stringify({ cmd, args, note: 'not implemented yet' }, null, 2));
process.exit(1);
