import type {MatchRatingsView,PublicAnalysis,PublicProtocol} from '../../api/domain';

// Отдельные указатели источников: у протокола, CV и рейтинга нет общей версии.
export type PlayerOrigin='protocol'|'cv'|'rating';
export type ReportContext={
 matchId:string;protocolPublicId:string|null;cvRunId:string|null;
 ratingSnapshotId:string|null;historicalRating:boolean;periodKey:string;
};
export type PlayerSelection={playerId:string;origin:PlayerOrigin};
export type Resource<T>={status:'loading'}|{status:'absent'}|
 {status:'error';message:string}|{status:'ready';value:T};
export type ReportModel={
 context:ReportContext;protocol:Resource<PublicProtocol>;
 cv:Resource<PublicAnalysis>;ratings:Resource<MatchRatingsView>;
};
