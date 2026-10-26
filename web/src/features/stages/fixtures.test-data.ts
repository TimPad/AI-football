import type {GroupView,PairView,SectionView,StageView} from './api';
export const team=(name:string)=>({entry_id:`e-${name}`,team_id:`t-${name}`,name,logo_id:null});
export const row=(name:string,place:number,zone:'advance'|'best'|null,tied=false)=>({place,team:team(name),played:3,won:2,drawn:0,lost:1,goals_for:7,goals_against:3,goal_diff:4,points:6,zone,tied});
export const group:GroupView={group_no:1,name:'Группа A',needs_lot:false,rows:[row('Север',1,'advance'),row('Юг',2,null)]};
export const side=(label:string,known=true)=>({label,team:known?team(label):null});
export const pair=(key:string,label:string,home:ReturnType<typeof side>,away:ReturnType<typeof side>,extra:Partial<PairView>={}):PairView=>({key,round_no:1,slot:1,bracket:'upper',group_no:null,label,home,away,bye:false,
 legs:[{match_id:null,fixture_id:null,leg:1,scheduled_at:null,status:null,score:null,shootout:null}],winner:null,note:null,can_schedule:false,changed:false,...extra});
export const sections:SectionView[]=[{key:'upper',name:'Сетка',rounds:[
 {round_no:1,name:'Полуфинал',pairs:[pair('U1-1','Полуфинал',side('Север'),side('Юг'),{winner:'home',legs:[{match_id:'m1',fixture_id:null,leg:1,scheduled_at:'2026-11-01T15:00:00Z',status:'ended',score:{home:3,away:1},shootout:null}]})]},
 {round_no:2,name:'Финал',pairs:[pair('U2-1','Финал',side('Север'),side('Победитель пары 2',false),{round_no:2})]}]}];
export const groupsStage:StageView={id:'s1',position:1,name:'Групповой этап',kind:'groups',status:'draft',criteria:['points','h2h_points','goal_diff','lot'],
 config:{kind:'groups',group_count:2,source:{entries:'all'}},regulation_id:'r1',revision:0,draw:null,groups:[],sections:[],can_next_round:false};
