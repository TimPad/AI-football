import {defineConfig} from '@playwright/test';
const baseURL=`http://127.0.0.1:${process.env.AIF_E2E_PORT??'8181'}`;
export default defineConfig({testDir:'./e2e',fullyParallel:false,workers:1,timeout:60000,expect:{timeout:10000},use:{baseURL,viewport:{width:1440,height:1000},trace:'retain-on-failure',screenshot:'only-on-failure'},webServer:{command:'../.venv/bin/python ../scripts/run_service_e2e.py',url:`${baseURL}/api/v1/ready`,reuseExistingServer:process.env.AIF_REUSE_E2E==='1',timeout:60000},projects:[{name:'chromium',use:{browserName:'chromium'}}]});
