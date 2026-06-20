import { getSimulatorData, getVta35 } from "@/lib/data";
import Simulator from "@/components/Simulator";

export default async function SimulatorPage() {
  const [chains, vta] = await Promise.all([getSimulatorData(), getVta35()]);
  return <Simulator chains={chains} vta={vta} />;
}
