import {test,expect} from 'vitest';
import {publicContext,publicForward,publicBack} from './publicContext';
const tid='11111111-1111-4111-8111-111111111111',mid='22222222-2222-4222-8222-222222222222';
test('keeps local public context and drops unsafe or circular forward targets',()=>{
 const state={calendarReturn:'/?day=2026-10-20',tournamentReturn:`/watch/tournaments/${tid}?day=2026-10-20&hall_id=H`,teamReturn:`/watch/tournaments/${tid}/teams/${mid}`,matchReturn:`/watch/matches/${mid}?tab=players`};
 expect(publicForward(state,'team',`/watch/tournaments/${tid}/teams/${mid}?day=2026-10-20`).matchReturn).toBeUndefined();expect(publicForward(state,'match',`/watch/matches/${mid}?tab=players`).tournamentReturn).toBe(state.tournamentReturn);
 expect(publicContext({calendarReturn:'//other.test',tournamentReturn:'https://other.test',teamReturn:'/teams/private',matchReturn:'javascript:alert(1)'})).toEqual({});
});
test('back consumes the visited level so the next breadcrumb goes to the parent',()=>{
 const state={tournamentReturn:`/watch/tournaments/${tid}?day=2026-10-20`,teamReturn:`/watch/tournaments/${tid}/teams/${mid}`,matchReturn:`/watch/matches/${mid}?tab=players`};
 const match=publicBack(state,`/watch/players/${tid}`,['match','team'],{href:'/',label:'home'});
 expect(match.state.matchReturn).toBeUndefined();
 const team=publicBack(match.state,match.href,['team','tournament'],{href:'/',label:'home'});
 expect(team.state.teamReturn).toBeUndefined();expect(team.state.tournamentReturn).toBe(state.tournamentReturn);
});
