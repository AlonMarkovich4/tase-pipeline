import { getSimulatorData } from "@/lib/data";
import Simulator from "@/components/Simulator";

export default async function SimulatorPage() {
  const chains = await getSimulatorData();
  return <Simulator chains={chains} />;
}
