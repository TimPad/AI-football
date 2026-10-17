import {expect,type Page} from '@playwright/test';
import {execFileSync} from 'node:child_process';
export async function verifiedCaptain(page:Page,email:string){
 await page.goto('/captain/login');const origin=new URL(page.url()).origin;const password='synthetic-captain-password';
 const registered=await page.request.post('/api/v1/captain/auth/register',{headers:{Origin:origin},data:{request_id:crypto.randomUUID(),display_name:'Капитан проверки',email,password}});expect(registered.status()).toBe(202);
 const mail=JSON.parse(execFileSync('../.venv/bin/python',['../scripts/captain_e2e_mail.py','--email',email],{encoding:'utf8'}));const token=new URLSearchParams(new URL(mail.url).hash.slice(1)).get('token');const verified=await page.request.post('/api/v1/captain/auth/verify',{headers:{Origin:origin},data:{request_id:crypto.randomUUID(),token}});expect(verified.ok()).toBe(true);
 await page.getByLabel('Email',{exact:true}).fill(email);await page.getByLabel('Пароль',{exact:true}).fill(password);await page.getByRole('button',{name:'Войти',exact:true}).click();await expect(page.getByRole('heading',{name:'Мои команды',exact:true})).toBeVisible();
 return (await page.request.get('/api/v1/captain/auth/me')).json();
}
