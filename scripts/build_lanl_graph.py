import argparse, json
from phigraph.validation.lanl.graph import export_graph_bundle
def main():
    p=argparse.ArgumentParser()
    p.add_argument("reduced_dir"); p.add_argument("--output",default="validation_results/lanl_graph")
    p.add_argument("--top-k",type=int,default=20); a=p.parse_args()
    print(json.dumps(export_graph_bundle(a.reduced_dir,a.output,a.top_k),indent=2))
if __name__=="__main__": main()
