import type {components} from '../../api/types';
export type ImportView=components['schemas']['ImportView'];
export type ImportResult=components['schemas']['ImportResult'];
export type ImportRow=components['schemas']['ImportRow'];
export type ImportConfig=Omit<components['schemas']['ImportPreviewInput'],'expected_revision'>;
export const FIELD_LABELS:Record<string,string>={team:'Команда',name:'ФИО',shirt_number:'Номер',position:'Амплуа',
 birth_date:'Дата рождения',height_cm:'Рост, см',weight_kg:'Вес, кг',last_name:'Фамилия',first_name:'Имя',patronymic:'Отчество'};
const ALIASES:Record<string,string>={команда:'team',названиекоманды:'team',фио:'name',игрок:'name',фамилияимяотчество:'name',
 номер:'shirt_number',номериґрока:'shirt_number',номеригрока:'shirt_number',амплуа:'position',позиция:'position',
 датарождения:'birth_date',др:'birth_date',рост:'height_cm',ростсм:'height_cm',вес:'weight_kg',вескг:'weight_kg',
 фамилия:'last_name',имя:'first_name',отчество:'patronymic'};
export function inferMapping(headers:string[]){const result:Record<string,number>={};headers.forEach((header,index)=>{
 const key=['№','#'].includes(header.trim())?'shirt_number':ALIASES[header.toLowerCase().replace(/[^\p{L}\p{N}]/gu,'')];
 if(key&&!(key in result))result[key]=index;
});return result}
export function initialConfig(value:ImportView):ImportConfig{
 const stored=value.configuration as Partial<ImportConfig>;
 return {sheet:stored.sheet??value.sheets[0]?.name??'',mapping:stored.mapping??inferMapping(value.sheets[0]?.headers??[]),
  edits:stored.edits??{},decisions:stored.decisions??{},team_decisions:stored.team_decisions??{},excluded_rows:stored.excluded_rows??[]};
}
