import { Stage } from "./stage/Scene"
import { scene as exfil } from "./scenes/Exfil"
import { scene as hero } from "./scenes/Hero"
import { scene as jail } from "./scenes/Jail"
import { scene as playground } from "./scenes/Playground"
import { scene as ship } from "./scenes/Ship"
import { scene as skill } from "./scenes/SkillText"
import { scene as verdict } from "./scenes/Verdict"

export function App() {
  return <Stage scenes={[hero, skill, jail, exfil, verdict, ship, playground]} />
}
