"""Explicit live/offline acceptance runner. Stores no key and prints no raw provider error."""
import argparse
import json
from pathlib import Path
import resource
import sys
import time
from zipfile import ZipFile
from aifootball.processor.job import process_job
from aifootball.processor.qwen import QwenError
from aifootball.understanding.evaluate import evaluate_understanding


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job',type=Path);parser.add_argument('--video',type=Path)
    parser.add_argument('--labels',type=Path,required=True);parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--models',type=Path,default=Path('models'));parser.add_argument('--mode',choices=['native','frames'],default='native')
    parser.add_argument('--max-requests',type=int,default=8);parser.add_argument('--max-input-tokens',type=int,default=60000)
    parser.add_argument('--max-output-tokens',type=int,default=20000);parser.add_argument('--resume',action='store_true')
    parser.add_argument('--analysis-scope',choices=['unknown','full_match','continuous_excerpt','highlights'],default='unknown')
    parser.add_argument('--result',type=Path,help='Evaluate an existing result.zip without a paid API call')
    args=parser.parse_args();started=time.monotonic();args.work_dir.mkdir(parents=True,exist_ok=True)
    result=args.result or args.work_dir/'result.zip'
    if args.result is None:
        if args.job is None or args.video is None:parser.error('--job and --video are required for live processing')
        try:
            process_job(args.job,args.video,result,models=args.models,understand=True,work_dir=args.work_dir/'processor',resume=args.resume,
                vlm_mode=args.mode,vlm_max_requests=args.max_requests,vlm_max_input_tokens=args.max_input_tokens,
                vlm_max_output_tokens=args.max_output_tokens,analysis_scope=args.analysis_scope)
        except QwenError as exc:
            parser.exit(2,f'Qwen acceptance unavailable: {exc.code}\n')
        except ValueError:
            parser.exit(2,'Acceptance unavailable: verify local API configuration, source, job and workspace.\n')
    from aifootball.analytics.exchange import validate_result
    validated=validate_result(result)
    if validated.understanding is None:parser.error('Result has no understanding document')
    predicted=validated.understanding
    report=evaluate_understanding(predicted,json.loads(args.labels.read_text()))
    report.update({'mode':args.mode,'wall_s':time.monotonic()-started,'process_peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024),
                   'usage':predicted['budget'],'evaluation_only':args.result is not None,
                   'analysis_scope':predicted['source']['analysis_scope'],'manual_review_seconds':None,
                   'sports_accuracy_validated':False})
    # A numerical report alone does not establish independent/control annotation quality.
    target=args.work_dir/f"acceptance-{report['split']}-{args.mode}.json"
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(f'Acceptance report: {target}')


if __name__=='__main__':main()
